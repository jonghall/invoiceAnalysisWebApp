from flask import render_template, flash, redirect, url_for, request, jsonify, send_file, after_this_request
from invoiceAnalysis import app
from invoiceAnalysis.forms import InvoiceAnalysisRequest
from invoiceAnalysis.getInvoices import *
import threading, os

@app.route('/', methods=['GET', 'POST'])
def index():
    global IC_API_KEY
    form=InvoiceAnalysisRequest(request.form)
    if request.method == 'POST' and form.validate():
        filename=runAnalysis(request.form.get("ic_api_key"), request.form.get("month"))
        return render_template("finished.html", filename=filename)
    return render_template("index.html", form=form)

@app.route('/download/<filename>')
def download_file(filename):
    file_path = "../" + filename
    return send_file(file_path, attachment_filename="invoiceAnalysis.xlsx", as_attachment=True)







