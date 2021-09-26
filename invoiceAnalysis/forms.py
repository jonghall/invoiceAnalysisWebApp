from wtforms import Form, StringField, validators

class InvoiceAnalysisRequest(Form):
    ic_api_key = StringField('IBM Cloud ApiKey:', [validators.Length(min=4, max=45)])
    month = StringField("Invoice month (YYYY-MM):", [validators.Length(min=7, max=7)])

