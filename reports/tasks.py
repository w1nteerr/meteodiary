"""Задачи Celery (ТЗ 4.7.3): генерация отчётов, очистка старых файлов."""
import csv
import io
from datetime import timedelta
from celery import shared_task
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone
from django.utils.timezone import localtime

from core.services import notify
from core.models import Notification


def dash(v):
    """Пустое значение (поле не заполняется этим типом наблюдения) — прочерк.
    Обычная вспомогательная функция, не задача Celery."""
    return "—" if v is None else f"{v}"


@shared_task
def generate_report(report_id):
    from observations.models import Observation, Status
    from .models import Report
    rep = Report.objects.select_related("station", "user").get(pk=report_id)
    qs = (Observation.objects.filter(
            status=Status.APPROVED, is_archived=False,
            observed_at__date__gte=rep.date_from, observed_at__date__lte=rep.date_to)
          .select_related("station", "station__owner", "precipitation_type")
          .order_by("observed_at"))
    if rep.station_id:
        qs = qs.filter(station_id=rep.station_id)
    rows = list(qs)
    if not rows:
        rep.state = Report.State.EMPTY
        rep.save(update_fields=["state"])
        notify(rep.user, "Отчёт: за выбранный период данных нет.",
               ntype=Notification.Type.REPORT)
        return

    if rep.fmt == Report.Fmt.CSV:
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        # состав выходной информации по ТЗ 4.7.1 (с владельцем точки)
        w.writerow(["Дата", "Точка", "Владелец точки", "t,°C", "Давление,гПа",
                    "Осадки", "Кол-во,мм", "Ветер,м/с", "Облачность,%", "Статус"])
        for o in rows:
            owner = o.station.owner
            owner_name = "Анонимный пользователь" if owner.is_deleted else owner.username
            w.writerow([localtime(o.observed_at).strftime("%Y-%m-%d %H:%M"), o.station.name, owner_name,
                        dash(o.temperature), dash(o.pressure),
                        o.precipitation_type.name if o.precipitation_type_id else "",
                        dash(o.precipitation_amount), dash(o.wind_speed), dash(o.cloudiness),
                        o.get_status_display()])
        content = buf.getvalue().encode("utf-8-sig")
        rep.file.save(f"report_{rep.pk}.csv", ContentFile(content), save=False)
    else:
        content = _build_pdf(rep, rows)
        rep.file.save(f"report_{rep.pk}.pdf", ContentFile(content), save=False)

    rep.state = Report.State.READY
    rep.save()
    notify(rep.user, "Отчёт сформирован и доступен в разделе «Мои отчёты».",
           ntype=Notification.Type.REPORT, link=reverse("report_list"))


def _build_pdf(rep, rows):
    """Структура PDF по ТЗ FR-008: титульная часть, сводка, таблица наблюдений.
    Шрифты DejaVu (кириллица) поставляются вместе с проектом (static/fonts) —
    без регистрации TTF стандартные шрифты ReportLab печатают квадраты."""
    import io as _io
    from django.conf import settings
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    fonts_dir = settings.BASE_DIR / "static" / "fonts"
    pdfmetrics.registerFont(TTFont("DejaVu", str(fonts_dir / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(fonts_dir / "DejaVuSans-Bold.ttf")))

    ACCENT = colors.HexColor("#0369a1")   # небесный синий, как на сайте
    GREY = colors.HexColor("#66718a")
    LINE = colors.HexColor("#d9e2ef")
    ZEBRA = colors.HexColor("#f2f7fc")

    st_title = ParagraphStyle("t", fontName="DejaVu-Bold", fontSize=17,
                              textColor=ACCENT, spaceAfter=8, leading=21)
    st_meta = ParagraphStyle("m", fontName="DejaVu", fontSize=9, textColor=GREY,
                             leading=15, spaceAfter=4)
    st_h = ParagraphStyle("h", fontName="DejaVu-Bold", fontSize=11, spaceBefore=12,
                          spaceAfter=6)
    st_cell = ParagraphStyle("c", fontName="DejaVu", fontSize=8, leading=10)

    buf = _io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=14 * mm, bottomMargin=16 * mm,
                            title="Дневник синоптика — отчёт")

    def footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont("DejaVu", 7.5)
        canvas.setFillColor(GREY)
        canvas.drawString(14 * mm, 9 * mm, "ИС «Дневник синоптика»")
        canvas.drawRightString(landscape(A4)[0] - 14 * mm, 9 * mm,
                               f"Страница {canvas.getPageNumber()}")
        canvas.restoreState()

    story = [Paragraph("Отчёт о метеонаблюдениях", st_title)]
    owner = rep.station.name if rep.station_id else "весь регион"
    story.append(Paragraph(
        f"Территория: {owner} &nbsp;·&nbsp; "
        f"Период: {rep.date_from:%d.%m.%Y} — {rep.date_to:%d.%m.%Y} &nbsp;·&nbsp; "
        f"Сформирован: {localtime(timezone.now()):%d.%m.%Y %H:%M} "
        f"пользователем {rep.user.username}", st_meta))
    story.append(Spacer(0, 4 * mm))

    # Сводка
    # экспресс/аллерго-наблюдения заполняют не все поля — агрегируем непустые.
    # Любой список может оказаться пустым (например, все замеры аллергические),
    # поэтому считаем через безопасные помощники, а не напрямую.
    temps = [float(o.temperature) for o in rows if o.temperature is not None]
    press = [float(o.pressure) for o in rows if o.pressure is not None]
    winds = [float(o.wind_speed) for o in rows if o.wind_speed is not None]
    psum = sum(float(o.precipitation_amount or 0) for o in rows)

    def agg(values, fn):
        """Агрегат по непустому списку, иначе прочерк."""
        return f"{fn(values):.1f}" if values else "—"

    sm = [["Наблюдений", "t мин, °C", "t средняя, °C", "t макс, °C",
           "Давление ср., гПа", "Ветер макс, м/с", "Осадки, мм"],
          [str(len(rows)),
           agg(temps, min),
           agg(temps, lambda v: sum(v) / len(v)),
           agg(temps, max),
           agg(press, lambda v: sum(v) / len(v)),
           agg(winds, max),
           f"{psum:.1f}"]]
    t = Table(sm, colWidths=[(landscape(A4)[0] - 28 * mm) / 7] * 7)
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "DejaVu"),
        ("FONTNAME", (0, 1), (-1, 1), "DejaVu-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7.5),
        ("FONTSIZE", (0, 1), (-1, 1), 11),
        ("TEXTCOLOR", (0, 0), (-1, 0), GREY),
        ("TEXTCOLOR", (0, 1), (-1, 1), ACCENT),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.4, LINE),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [Paragraph("Сводка за период", st_h), t,
              Paragraph("Наблюдения", st_h)]

    # Таблица наблюдений
    head = ["Дата и время", "Точка", "Владелец", "t, °C", "P, гПа",
            "Ветер, м/с", "Осадки", "мм", "Обл., %"]
    body = [head]
    for o in rows:
        ow = o.station.owner
        body.append([
            localtime(o.observed_at).strftime("%d.%m.%Y %H:%M"),
            Paragraph(o.station.name, st_cell),
            "Анонимный" if ow.is_deleted else ow.username,
            dash(o.temperature), dash(o.pressure), dash(o.wind_speed),
            o.precipitation_type.name if o.precipitation_type_id else "—",
            dash(o.precipitation_amount), dash(o.cloudiness)])
    widths = [30, 62, 28, 14, 18, 20, 26, 12, 15]
    k = (landscape(A4)[0] - 28 * mm) / sum(widths)
    t = Table(body, colWidths=[w * k for w in widths], repeatRows=1)
    style = [
        ("FONTNAME", (0, 0), (-1, 0), "DejaVu-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "DejaVu"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("ALIGN", (3, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]
    for i in range(1, len(body)):          # «зебра» для читаемости
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), ZEBRA))
    t.setStyle(TableStyle(style))
    story.append(t)

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


@shared_task
def cleanup_old_reports():
    """Периодическая задача (celery beat): удаление отчётов старше 7 суток (ТЗ FR-008)."""
    from django.conf import settings
    from .models import Report
    limit = timezone.now() - timedelta(days=settings.REPORT_TTL_DAYS)
    for rep in Report.objects.filter(created_at__lt=limit):
        if rep.file:
            rep.file.delete(save=False)
        rep.delete()
