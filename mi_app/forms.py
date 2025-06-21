# mi_app/forms.py

from django import forms

class RawFileUploadForm(forms.Form):
    raw_file = forms.FileField(label='Selecciona un archivo .raw')
