from flask import render_template, flash, redirect, url_for, request, jsonify, send_file
from invoiceAnalysis import app
from invoiceAnalysis.forms import InvoiceAnalysisRequest
from invoiceAnalysis.getInvoices import *
import threading, time

@app.route('/', methods=['GET', 'POST'])
def index():
    global IC_API_KEY
    form=InvoiceAnalysisRequest(request.form)
    if request.method == 'POST' and form.validate():
        flash('Thanks for submitting')
        logging.info("Starting runAnalysis Thread.")
        x = threading.Thread(target=runAnalysis, args=[request.form.get("ic_api_key"),request.form.get("month") ])
        x.start()
        while x.is_alive():
            time.sleep(1)
        return redirect(url_for('submitted'))
    return render_template("index.html", form=form)

@app.route('/submitted.html', methods=['GET'])
def submitted():
    return render_template("submitted.html")

@app.route('/download')
def download_file():
	path = "../invoiceAnalysis.xlsx"
	return send_file(path, as_attachment=True)







