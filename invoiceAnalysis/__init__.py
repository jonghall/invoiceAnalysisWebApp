from flask import Flask
from flask_bootstrap import Bootstrap


app = Flask(__name__, instance_relative_config=True)
app.config.from_object('config')
bootstrap = Bootstrap(app)

from invoiceAnalysis import routes
app.config.from_object('config')

from invoiceAnalysis.getInvoices import setup_logging

setup_logging()
