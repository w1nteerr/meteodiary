"""FR-008: заказ отчёта (период ≤ 1 года), список «Мои отчёты»."""
from datetime import timedelta
from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

from core.services import audit
from .models import Report
from .tasks import generate_report


class ReportForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ["station", "date_from", "date_to", "fmt"]
        widgets = {"date_from": forms.DateInput(attrs={"type": "date"}),
                   "date_to": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["station"].required = False
        from stations.models import Station
        self.fields["station"].queryset = Station.objects.filter(is_public=True, is_active=True)

    def clean(self):
        data = super().clean()
        df, dt = data.get("date_from"), data.get("date_to")
        if df and dt:
            if df > dt:
                raise forms.ValidationError("Дата начала позже даты окончания.")
            if (dt - df) > timedelta(days=settings.REPORT_MAX_PERIOD_DAYS):
                raise forms.ValidationError("Период выгрузки не может превышать 1 год.")
        return data


@login_required
def report_create(request):
    form = ReportForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        rep = form.save(commit=False)
        rep.user = request.user
        rep.save()
        audit(request, "report_request", obj=f"report:{rep.pk}")
        generate_report.delay(rep.pk)   # фоновая генерация (Celery; в dev — синхронно)
        messages.info(request, "Отчёт формируется. По готовности придёт уведомление.")
        return redirect("report_list")
    return render(request, "reports/form.html", {"form": form})


@login_required
def report_list(request):
    return render(request, "reports/list.html",
                  {"reports": request.user.reports.all()[:50]})
