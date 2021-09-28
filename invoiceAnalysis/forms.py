from wtforms import Form, StringField, validators, PasswordField, SubmitField

class InvoiceAnalysisRequest(Form):
    ic_api_key = PasswordField('IBM Cloud ApiKey:', [validators.Length(min=4, max=45)])
    month = StringField("Invoice month (YYYY-MM):", [validators.Length(min=7, max=7)])

