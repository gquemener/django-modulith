from django.urls import path

from . import views

app_name = "ticketing"

urlpatterns = [
    path("", views.my_tickets, name="my_tickets"),
    path("new/", views.open_ticket, name="open"),
    path("inbox/", views.inbox, name="inbox"),
    path("<uuid:ticket_id>/", views.ticket_detail, name="detail"),
    path("<uuid:ticket_id>/messages/", views.post_message, name="post_message"),
    path("<uuid:ticket_id>/escalate/", views.escalate, name="escalate"),
    path("<uuid:ticket_id>/close/", views.close, name="close"),
    path("<uuid:ticket_id>/reopen/", views.reopen, name="reopen"),
]
