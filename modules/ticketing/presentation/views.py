"""Thin HTTP adapters: parse input, call a use case, render or redirect."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..bootstrap import ticketing_service
from ..domain import ConcurrencyConflict, TicketDomainError, TicketNotFound
from ..infrastructure import queries
from .forms import MessageForm, OpenTicketForm


@login_required
def home(request):
    if queries.is_support_staff(request.user.pk):
        return redirect("ticketing:inbox")
    return redirect("ticketing:my_tickets")


@login_required
def my_tickets(request):
    return render(request, "ticketing/my_tickets.html", {
        "tickets": queries.customer_tickets(request.user.pk),
    })


@login_required
def inbox(request):
    if not queries.is_support_staff(request.user.pk):
        return redirect("ticketing:my_tickets")
    return render(request, "ticketing/inbox.html", queries.staff_inbox(request.user.pk))


@login_required
def open_ticket(request):
    form = OpenTicketForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            ticket_id = ticketing_service().open_ticket(
                customer_id=request.user.pk,
                title=form.cleaned_data["title"],
                description=form.cleaned_data["description"],
                priority=form.cleaned_data["priority"],
            )
        except TicketDomainError as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, "Your ticket has been opened.")
            return redirect("ticketing:detail", ticket_id=ticket_id)
    return render(request, "ticketing/open_ticket.html", {"form": form})


@login_required
def ticket_detail(request, ticket_id):
    try:
        details = queries.ticket_details(ticket_id, request.user.pk, timezone.now())
    except TicketNotFound:
        raise Http404 from None
    if details.viewer_role == "agent":
        _run(request, lambda s: s.record_opened(ticket_id, request.user.pk))
    return render(request, "ticketing/ticket_detail.html", {
        "ticket": details,
        "form": MessageForm(),
    })


@login_required
@require_POST
def post_message(request, ticket_id):
    form = MessageForm(request.POST)
    if form.is_valid():
        _run(request, lambda s: s.post_message(ticket_id, request.user.pk, form.cleaned_data["body"]))
    else:
        messages.error(request, "A message cannot be empty.")
    return redirect("ticketing:detail", ticket_id=ticket_id)


@login_required
@require_POST
def escalate(request, ticket_id):
    if _run(request, lambda s: s.escalate(ticket_id, request.user.pk)):
        messages.success(request, "The ticket has been escalated to the agent's manager.")
    return redirect("ticketing:detail", ticket_id=ticket_id)


@login_required
@require_POST
def close(request, ticket_id):
    if _run(request, lambda s: s.close(ticket_id, request.user.pk)):
        messages.success(request, "The ticket has been closed.")
    return redirect("ticketing:detail", ticket_id=ticket_id)


@login_required
@require_POST
def reopen(request, ticket_id):
    if _run(request, lambda s: s.reopen(ticket_id, request.user.pk)):
        messages.success(request, "The ticket has been reopened.")
    return redirect("ticketing:detail", ticket_id=ticket_id)


def _run(request, use_case) -> bool:
    """Run a use case, turning domain errors into user-facing messages."""
    try:
        use_case(ticketing_service())
    except TicketNotFound:
        raise Http404 from None
    except ConcurrencyConflict:
        messages.error(request, "The ticket was updated by someone else. Please try again.")
    except TicketDomainError as error:
        messages.error(request, str(error))
    else:
        return True
    return False
