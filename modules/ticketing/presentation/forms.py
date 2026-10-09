from django import forms

from ..domain import Priority


class OpenTicketForm(forms.Form):
    title = forms.CharField(max_length=200)
    priority = forms.ChoiceField(
        choices=[(p.value, p.name.title()) for p in Priority], initial=Priority.MEDIUM.value
    )
    description = forms.CharField(widget=forms.Textarea(attrs={"rows": 6}))


class MessageForm(forms.Form):
    body = forms.CharField(label="Message", widget=forms.Textarea(attrs={"rows": 4}))
