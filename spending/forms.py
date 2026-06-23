from django import forms

from .models import Spending


class SpendingForm(forms.ModelForm):
    class Meta:
        model = Spending
        fields = ['date', 'description', 'amount', 'currency', 'tag']
        widgets = {
            'date': forms.HiddenInput(),
            'description': forms.TextInput(attrs={'placeholder': 'What was this for?'}),
            'amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'tag': forms.TextInput(attrs={'list': 'tag-datalist', 'maxlength': '50'}),
        }

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount <= 0:
            raise forms.ValidationError('Amount must be greater than zero.')
        return amount

    def clean_tag(self):
        tag = self.cleaned_data.get('tag', '')
        if tag is None:
            return ''
        return tag.strip()
