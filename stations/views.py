"""FR-004 создание точки, FR-014 управление точками (редактирование, архивация, удаление)."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404

from core.services import audit
from .forms import StationForm
from .models import Station


def station_public(request, pk):
    """Публичная страница точки: сведения и история подтверждённых наблюдений
    (аналог персонального архива станции на платформах типа WOW)."""
    from django.core.paginator import Paginator
    from observations.models import Status
    st = get_object_or_404(Station, pk=pk)
    is_owner = request.user.is_authenticated and st.owner_id == request.user.pk
    if not st.is_public and not is_owner:
        from django.http import Http404
        raise Http404
    qs = (st.observations.filter(status=Status.APPROVED, is_archived=False)
          .select_related("precipitation_type").order_by("-observed_at"))
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    temps = [float(o.temperature) for o in qs[:500] if o.temperature is not None]
    summary = None
    if temps:
        summary = {"count": qs.count(), "t_min": min(temps), "t_max": max(temps),
                   "t_avg": round(sum(temps) / len(temps), 1)}
    return render(request, "stations/public.html",
                  {"st": st, "page": page, "summary": summary, "is_owner": is_owner})


@login_required
def station_list(request):
    stations = request.user.stations.order_by("-is_active", "name")
    return render(request, "stations/list.html", {"stations": stations})


@login_required
def station_create(request):
    form = StationForm(request.POST or None, owner=request.user)
    if request.method == "POST" and form.is_valid():
        st = form.save(commit=False)
        st.owner = request.user
        st.save()
        audit(request, "station_create", obj=f"station:{st.pk}")
        messages.success(request, "Точка наблюдения создана.")
        return redirect("station_list")
    return render(request, "stations/form.html", {"form": form, "title": "Новая точка наблюдения"})


@login_required
def station_edit(request, pk):
    st = get_object_or_404(Station, pk=pk, owner=request.user)
    # FR-014: изменение координат — только если нет подтверждённых наблюдений
    has_approved = st.observations.filter(status="approved").exists()
    form = StationForm(request.POST or None, instance=st, owner=request.user)
    if request.method == "POST" and form.is_valid():
        if has_approved and ({"latitude", "longitude"} & set(form.changed_data)):
            messages.error(request, "У точки есть подтверждённые наблюдения — координаты менять "
                                    "нельзя. Архивируйте точку и создайте новую.")
        else:
            form.save()
            audit(request, "station_edit", obj=f"station:{st.pk}")
            messages.success(request, "Точка обновлена.")
            return redirect("station_list")
    return render(request, "stations/form.html",
                  {"form": form, "title": f"Точка «{st.name}»", "has_approved": has_approved})


@login_required
def station_toggle_archive(request, pk):
    st = get_object_or_404(Station, pk=pk, owner=request.user)
    if request.method == "POST":
        st.is_active = not st.is_active
        st.save(update_fields=["is_active", "updated_at"])
        audit(request, "station_archive" if not st.is_active else "station_unarchive",
              obj=f"station:{st.pk}")
        messages.success(request, "Статус точки изменён.")
    return redirect("station_list")


@login_required
def station_delete(request, pk):
    st = get_object_or_404(Station, pk=pk, owner=request.user)
    if request.method == "POST":
        if st.observations.exists():
            messages.error(request, "У точки есть наблюдения — доступна только архивация.")
        else:
            audit(request, "station_delete", obj=f"station:{st.pk}")
            st.delete()
            messages.success(request, "Точка удалена.")
    return redirect("station_list")
