#################################################################################################
# Author: Jon Hall
# Copyright (c) 2021
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#################################################################################################

import SoftLayer, os, logging, logging.config, json, calendar, uuid, os.path, pytz
import pandas as pd
import numpy as np
from flask import Flask, render_template, request, send_file, jsonify, session,after_this_request
from celery import Celery
from flask_bootstrap import Bootstrap
from forms import InvoiceAnalysisRequest
from datetime import datetime, tzinfo, timezone
from dateutil import tz
from calendar import monthrange
from dateutil.relativedelta import relativedelta
from ibm_platform_services import IamIdentityV1, UsageReportsV4
from ibm_cloud_sdk_core import ApiException
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
app = Flask(__name__)
app.config.from_object('config')

# get simple environ, otherwise if code engine extract env from binding
if os.environ.get("REDIS_USER") != None:
    app.config["broker_transport"] = "rediss"
    app.config['broker_url'] = "rediss://" + os.environ.get("REDIS_USER") + ":" + os.environ.get("REDIS_PW") + "@" + os.environ.get("REDIS_CONNECTION") + "?ssl_cert_reqs=required&ssl_ca_certs=" + os.environ.get("REDIS_CERTFILE")
    app.config['result_backend'] = "rediss://" + os.environ.get("REDIS_USER") + ":" + os.environ.get("REDIS_PW")+ "@" + os.environ.get("REDIS_CONNECTION") + "?ssl_cert_reqs=required&ssl_ca_certs="+ os.environ.get("REDIS_CERTFILE")
else:
    # extract from codeengine environment
    redis_connection = json.loads(os.environ.get('DATABASES_FOR_REDIS_CONNECTION'))
    cert_name = redis_connection["cli"]["certificate"]["name"]
    app.config["broker_transport"] = "rediss"
    app.config['broker_url'] =  redis_connection["cli"]["arguments"][0][1] + "?ssl_cert_reqs=required&ssl_ca_certs=/certs/" + cert_name
    app.config['result_backend'] = redis_connection["cli"]["arguments"][0][1] + "?ssl_cert_reqs=required&ssl_ca_certs=/certs/" + cert_name

celery = Celery(app.name)
celery.conf.update(app.config)
bootstrap = Bootstrap(app)

def setup_logging(default_path='logging.json', default_level=logging.info, env_key='LOG_CFG'):
    path = default_path
    value = os.getenv(env_key, None)
    if value:
        path = value
    if os.path.exists(path):
        with open(path, 'rt') as f:
            config = json.load(f)
        logging.config.dictConfig(config)
    else:
        logging.basicConfig(level=default_level)

def getDescription(categoryCode, detail):
    for item in detail:
        if 'categoryCode' in item:
            if item['categoryCode'] == categoryCode:
                return item['product']['description'].strip()
    return ""

def getStorageServiceUsage(categoryCode, detail):
    for item in detail:
        if 'categoryCode' in item:
            if item['categoryCode'] == categoryCode:
                return item['description'].strip()
    return ""


def getCFTSInvoiceDate(invoiceDate):
    # Determine CFTS Invoice Month (20th of prev month - 19th of current month) are on current month CFTS invoice.
    if invoiceDate.day > 19:
        invoiceDate = invoiceDate + relativedelta(months=1)
    return invoiceDate.strftime('%Y-%m')

def getInvoiceDates(startdate,enddate):
    # Adjust start and dates to match CFTS Invoice cutoffs of 20th to end of day 19th 00:00 Dallas time on the 20th
    dallas = tz.gettz('US/Central')
    startdate = datetime(int(startdate[0:4]),int(startdate[5:7]),20,0,0,0,tzinfo=dallas) - relativedelta(months=1)
    enddate = datetime(int(enddate[0:4]),int(enddate[5:7]),20,0,0,0,tzinfo=dallas)
    return startdate, enddate

def getInvoiceList(startdate, enddate):
    # GET LIST OF PORTAL INVOICES BETWEEN DATES USING CENTRAL (DALLAS) TIME
    error=None
    dallas=tz.gettz('US/Central')
    logging.info("Looking up invoices from {} to {}.".format(startdate.strftime("%m/%d/%Y %H:%M:%S%z"), enddate.strftime("%m/%d/%Y %H:%M:%S%z")))
    # filter invoices based on local dallas time that correspond to CFTS UTC cutoff
    try:
        invoiceList = client['Account'].getInvoices(mask='id,createDate,typeCode,invoiceTotalAmount,invoiceTotalRecurringAmount,invoiceTopLevelItemCount', filter={
                'invoices': {
                    'createDate': {
                        'operation': 'betweenDate',
                        'options': [
                             {'name': 'startDate', 'value': [startdate.astimezone(dallas).strftime("%m/%d/%Y %H:%M:%S")]},
                             {'name': 'endDate', 'value': [enddate.astimezone(dallas).strftime("%m/%d/%Y %H:%M:%S")]}
                        ]
                    }
                }
        })
    except SoftLayer.SoftLayerAPIError as e:
        logging.error("Account::getInvoices: %s, %s" % (e.faultCode, e.faultString))
        error = ("Account::getInvoices: %s, %s" % (e.faultCode, e.faultString))
        return None, error
    return invoiceList, error

def getInvoiceDetail(IC_API_KEY, startdate, enddate):
    #
    # GET InvoiceDetail
    #
    global client, SL_ENDPOINT

    # Create dataframe to work with for classic infrastructure invoices
    df = pd.DataFrame(columns=['Portal_Invoice_Date',
                               'Portal_Invoice_Time',
                               'Service_Date_Start',
                               'Service_Date_End',
                               'IBM_Invoice_Month',
                               'Portal_Invoice_Number',
                               'Type',
                               'BillingItemId',
                               'hostName',
                               'Category',
                               'Description',
                               'Memory',
                               'OS',
                               'Hourly',
                               'Usage',
                               'Hours',
                               'HourlyRate',
                               'totalRecurringCharge',
                               'NewEstimatedMonthly',
                               'totalOneTimeAmount',
                               'InvoiceTotal',
                               'InvoiceRecurring',
                               'Recurring_Description'])

    error = None
    # Change endpoint to private Endpoint if command line open chosen
    SL_ENDPOINT = "https://api.softlayer.com/xmlrpc/v3.1"
    dallas = tz.gettz('US/Central')
    # Create Classic infra API client
    client = SoftLayer.Client(username="apikey", api_key=IC_API_KEY, endpoint_url=SL_ENDPOINT)

    # get list of invoices between start date and enddate
    invoiceList, error = getInvoiceList(startdate, enddate)
    if invoiceList == None:
        return invoiceList, error

    for invoice in invoiceList:
        if float(invoice['invoiceTotalAmount']) == 0:
            continue

        invoiceID = invoice['id']
        # To align to CFTS billing cutoffs display time in Dallas timezone.
        invoiceDate = datetime.strptime(invoice['createDate'], "%Y-%m-%dT%H:%M:%S%z").astimezone(dallas)
        invoiceTotalAmount = float(invoice['invoiceTotalAmount'])
        CFTSInvoiceDate = getCFTSInvoiceDate(invoiceDate)

        invoiceTotalRecurringAmount = float(invoice['invoiceTotalRecurringAmount'])
        invoiceType = invoice['typeCode']
        recurringDesc = ""
        if invoiceType == "NEW":
            serviceDateStart = invoiceDate
            # get last day of month
            serviceDateEnd= serviceDateStart.replace(day=calendar.monthrange(serviceDateStart.year,serviceDateStart.month)[1])

        if invoiceType == "CREDIT" or invoiceType == "ONE-TIME-CHARGE":
            serviceDateStart = invoiceDate
            serviceDateEnd = invoiceDate

        totalItems = invoice['invoiceTopLevelItemCount']

        # PRINT INVOICE SUMMARY LINE
        logging.info('Invoice: {} Date: {} Type:{} Items: {} Amount: ${:,.2f}'.format(invoiceID, datetime.strftime(invoiceDate, "%Y-%m-%d"), invoiceType, totalItems, invoiceTotalRecurringAmount))

        limit = 250 ## set limit of record returned
        for offset in range(0, totalItems, limit):
            if ( totalItems - offset - limit ) < 0:
                remaining = totalItems - offset
            logging.info("Retrieving %s invoice line items for Invoice %s at Offset %s of %s" % (limit, invoiceID, offset, totalItems))

            try:
                Billing_Invoice = client['Billing_Invoice'].getInvoiceTopLevelItems(id=invoiceID, limit=limit, offset=offset,
                                    mask="id, billingItemId, categoryCode, category.name, hourlyFlag, hostName, domainName, product.description," \
                                         "createDate, totalRecurringAmount, totalOneTimeAmount, usageChargeFlag, hourlyRecurringFee," \
                                         "children.description, children.categoryCode, children.product, children.hourlyRecurringFee")
            except SoftLayer.SoftLayerAPIError as e:
                logging.error("Billing_Invoice::getInvoiceTopLevelItems: %s, %s" % (e.faultCode, e.faultString))
                error =("Billing_Invoice::getInvoiceTopLevelItems: %s, %s" % (e.faultCode, e.faultString))
                return df, error

            count = 0
            # ITERATE THROUGH DETAIL
            for item in Billing_Invoice:
                totalOneTimeAmount = float(item['totalOneTimeAmount'])
                billingItemId = item['billingItemId']
                category = item["categoryCode"]
                categoryName = item["category"]["name"]
                description = item['product']['description']
                memory = getDescription("ram", item["children"])
                os = getDescription("os", item["children"])

                if 'hostName' in item:
                    if 'domainName' in item:
                        hostName = item['hostName']+"."+item['domainName']
                    else:
                        hostName = item['hostName']
                else:
                    hostName = ""

                recurringFee = float(item['totalRecurringAmount'])
                NewEstimatedMonthly = 0

                # If Hourly calculate hourly rate and total hours
                if item["hourlyFlag"]:
                    # if hourly charges are previous month usage
                    serviceDateStart = invoiceDate - relativedelta(months=1)
                    serviceDateEnd = serviceDateStart.replace(day=calendar.monthrange(serviceDateStart.year, serviceDateStart.month)[1])
                    recurringDesc = "IaaS Usage"
                    hourlyRecurringFee = 0
                    hours = 0
                    if "hourlyRecurringFee" in item:
                        if float(item["hourlyRecurringFee"]) > 0:
                            hourlyRecurringFee = float(item['hourlyRecurringFee'])
                            for child in item["children"]:
                                if "hourlyRecurringFee" in child:
                                    hourlyRecurringFee = hourlyRecurringFee + float(child['hourlyRecurringFee'])
                            hours = round(float(recurringFee) / hourlyRecurringFee)            # Not an hourly billing item
                else:
                    if categoryName.find("Platform Service Plan") != -1:
                        # Non Hourly PaaS Usage from actual usage two months prior
                        serviceDateStart = invoiceDate - relativedelta(months=2)
                        serviceDateEnd = serviceDateStart.replace(day=calendar.monthrange(serviceDateStart.year, serviceDateStart.month)[1])
                        recurringDesc = "Platform Service Usage"
                    else:
                        if invoiceType == "RECURRING":
                            serviceDateStart = invoiceDate
                            serviceDateEnd = serviceDateStart.replace(day=calendar.monthrange(serviceDateStart.year, serviceDateStart.month)[1])
                            recurringDesc = "IaaS Monthly"
                    hourlyRecurringFee = 0
                    hours = 0

                # Special handling for storage
                if category == "storage_service_enterprise":
                    iops = getDescription("storage_tier_level", item["children"])
                    storage = getDescription("performance_storage_space", item["children"])
                    snapshot = getDescription("storage_snapshot_space", item["children"])
                    if snapshot == "":
                        description = storage + " " + iops + " "
                    else:
                        description = storage+" " + iops + " with " + snapshot
                elif category == "performance_storage_iops":
                    iops = getDescription("performance_storage_iops", item["children"])
                    storage = getDescription("performance_storage_space", item["children"])
                    description = storage + " " + iops
                elif category == "storage_as_a_service":
                    if item["hourlyFlag"]:
                        model = "Hourly"
                        for child in item["children"]:
                            if "hourlyRecurringFee" in child:
                                hourlyRecurringFee = hourlyRecurringFee + float(child['hourlyRecurringFee'])
                        if hourlyRecurringFee>0:
                            hours = round(float(recurringFee) / hourlyRecurringFee)
                        else:
                            hours = 0
                    else:
                        model = "Monthly"
                    space = getStorageServiceUsage('performance_storage_space', item["children"])
                    tier = getDescription("storage_tier_level", item["children"])
                    snapshot = getDescription("storage_snapshot_space", item["children"])
                    if space == "" or tier == "":
                        description = model + " File Storage"
                    else:
                        if snapshot == "":
                            description = model + " File Storage "+ space + " at " + tier
                        else:
                            snapshotspace = getStorageServiceUsage('storage_snapshot_space', item["children"])
                            description = model + " File Storage " + space + " at " + tier + " with " + snapshotspace
                elif category == "guest_storage":
                        imagestorage = getStorageServiceUsage("guest_storage_usage", item["children"])
                        if imagestorage == "":
                            description = description.replace('\n', " ")
                        else:
                            description = imagestorage
                else:
                    description = description.replace('\n', " ")


                if invoiceType == "NEW":
                    # calculate non pro-rated amount for use in forecast
                    daysInMonth = monthrange(invoiceDate.year, invoiceDate.month)[1]
                    daysLeft = daysInMonth - invoiceDate.day + 1
                    dailyAmount = recurringFee / daysLeft
                    NewEstimatedMonthly = dailyAmount * daysInMonth
                # Append record to dataframe
                row = {'Portal_Invoice_Date': invoiceDate.strftime("%Y-%m-%d"),
                       'Portal_Invoice_Time': invoiceDate.strftime("%H:%M:%S%z"),
                       'Service_Date_Start': serviceDateStart.strftime("%Y-%m-%d"),
                       'Service_Date_End': serviceDateEnd.strftime("%Y-%m-%d"),
                       'IBM_Invoice_Month': CFTSInvoiceDate,
                       'Portal_Invoice_Number': invoiceID,
                       'BillingItemId': billingItemId,
                       'hostName': hostName,
                       'Category': categoryName,
                       'Description': description,
                       'Memory': memory,
                       'OS': os,
                       'Hourly': item["hourlyFlag"],
                       'Usage': item["usageChargeFlag"],
                       'Hours': hours,
                       'HourlyRate': round(hourlyRecurringFee,5),
                       'totalRecurringCharge': round(recurringFee,3),
                       'totalOneTimeAmount': float(totalOneTimeAmount),
                       'NewEstimatedMonthly': float(NewEstimatedMonthly),
                       'InvoiceTotal': float(invoiceTotalAmount),
                       'InvoiceRecurring': float(invoiceTotalRecurringAmount),
                       'Type': invoiceType,
                       'Recurring_Description': recurringDesc
                        }

                df = df.append(row, ignore_index=True)
    return df, error

def createReport(filename, classicUsage, paasUsage):
    # Write dataframe to excel
    logging.info("Creating Pivots File.")
    writer = pd.ExcelWriter(filename, engine='xlsxwriter')
    workbook = writer.book

    #
    # Write detail tab
    #
    classicUsage.to_excel(writer, 'Detail')
    usdollar = workbook.add_format({'num_format': '$#,##0.00'})
    worksheet = writer.sheets['Detail']
    worksheet.set_column('Q:W', 18, usdollar)
    totalrows,totalcols=classicUsage.shape
    worksheet.autofilter(0,0,totalrows,totalcols)

    #
    # Map Portal Invoices to SLIC Invoices / Create Top Sheet per SLIC month
    #

    classicUsage["totalAmount"] = classicUsage["totalOneTimeAmount"] + classicUsage["totalRecurringCharge"]

    months = classicUsage.IBM_Invoice_Month.unique()
    for i in months:
        logging.info("Creating top sheet for %s." % (i))
        ibminvoicemonth = classicUsage.query('IBM_Invoice_Month == @i')
        SLICInvoice = pd.pivot_table(ibminvoicemonth,
                                     index=["Type", "Portal_Invoice_Number", "Service_Date_Start", "Service_Date_End", "Recurring_Description"],
                                     values=["totalAmount"],
                                     aggfunc={'totalAmount': np.sum}, fill_value=0).sort_values(by=['Service_Date_Start', "Portal_Invoice_Number"])

        out = pd.concat([d.append(d.sum().rename((k, ' ', ' ', 'Subtotal', ' '))) for k, d in SLICInvoice.groupby('Type')]).append(SLICInvoice.sum().rename((' ', ' ', ' ', 'Pay this Amount', '')))
        out.rename(columns={"Type": "Invoice Type", "Portal_Invoice_Number": "Invoice",
                            "Service_Date_Start": "Service Start", "Service_Date_End": "Service End",
                             "Recurring_Description": "Description", "totalAmount": "Amount"}, inplace=True)
        out.to_excel(writer, 'TopSheet-{}'.format(i))
        worksheet = writer.sheets['TopSheet-{}'.format(i)]
        format1 = workbook.add_format({'num_format': '$#,##0.00'})
        format2 = workbook.add_format({'align': 'left'})
        worksheet.set_column("A:E", 20, format2)
        worksheet.set_column("F:F", 18, format1)

    #
    # Build a pivot table by for Forecasting NEW invoices form 1st to 20th and add to last Recurring Invoice to estimate
    # what the next recurringInvoice will be.   Uses estimated monthly charges from all NEW invoices which occurred after
    # the recurring invoice.   This forecast assumes, no deprovisioning and NEW additional invoices after 19th.
    invoicemonth = months[-1]
    newstart = invoicemonth + "-01"
    newend = invoicemonth + "-19"
    forecastR = classicUsage.query('IBM_Invoice_Month == @invoicemonth and Type == "RECURRING"')[['Portal_Invoice_Date', 'IBM_Invoice_Month','Type','Category','totalAmount']]
    forecastN = classicUsage.query('IBM_Invoice_Month == @invoicemonth and Type == "NEW" and Portal_Invoice_Date >= @newstart and Portal_Invoice_Date <= @newend ')[['Portal_Invoice_Date', 'IBM_Invoice_Month','Type','Category','NewEstimatedMonthly']]
    result = forecastR.append(forecastN).fillna(0)
    sum_column = result["totalAmount"] + result["NewEstimatedMonthly"]
    result["nextRecurring"] = sum_column
    if len(result) > 0:
        newForecast = pd.pivot_table(result, index=["Category"],
                                     values=["totalAmount", "NewEstimatedMonthly", "nextRecurring"],
                                     aggfunc={'totalAmount': np.sum, 'NewEstimatedMonthly': np.sum, 'nextRecurring': np.sum }, margins=True, margins_name='Total', fill_value=0). \
            rename(columns={'totalAmount': 'lastRecurringInvoice', 'NewEstimatedMonthly': 'NewEstimatedCharges'})

        column_order = ['lastRecurringInvoice', 'NewEstimatedCharges', 'nextRecurring']
        newForecast = newForecast.reindex(column_order, axis=1)
        newForecast.to_excel(writer, 'recurringForecast')
        worksheet = writer.sheets['recurringForecast']
        format1 = workbook.add_format({'num_format': '$#,##0.00'})
        format2 = workbook.add_format({'align': 'left'})
        worksheet.set_column("A:A", 40, format2)
        worksheet.set_column("B:D", 25, format1)

    #
    # Build a pivot table by Invoice Type
    #
    if len(classicUsage)>0:
        invoiceSummary = pd.pivot_table(classicUsage, index=["Type", "Category"],
                                        values=["totalAmount"],
                                        columns=['IBM_Invoice_Month'],
                                        aggfunc={'totalAmount': np.sum,}, margins=True, margins_name="Total", fill_value=0).\
                                        rename(columns={'totalRecurringCharge': 'TotalRecurring'})
        invoiceSummary.to_excel(writer, 'InvoiceSummary')
        worksheet = writer.sheets['InvoiceSummary']
        format1 = workbook.add_format({'num_format': '$#,##0.00'})
        format2 = workbook.add_format({'align': 'left'})
        worksheet.set_column("A:A", 20, format2)
        worksheet.set_column("B:B", 40, format2)
        worksheet.set_column("C:ZZ", 18, format1)


    #
    # Build a pivot table by Category with totalRecurringCharges

    if len(classicUsage)>0:
        categorySummary = pd.pivot_table(classicUsage, index=["Type", "Category", "Description"],
                                         values=["totalAmount"],
                                         columns=['IBM_Invoice_Month'],
                                         aggfunc={'totalAmount': np.sum}, margins=True, margins_name="Total", fill_value=0)
        categorySummary.to_excel(writer, 'CategorySummary')
        worksheet = writer.sheets['CategorySummary']
        format1 = workbook.add_format({'num_format': '$#,##0.00'})
        format2 = workbook.add_format({'align': 'left'})
        worksheet.set_column("A:A", 40, format2)
        worksheet.set_column("B:B", 40, format2)
        worksheet.set_column("C:ZZ", 18, format1)

    #
    # Build a pivot table by for Forecasting
    #logging.info("Creating forecast worksheet.")
    #forecast = classicUsage.query('IBM_Invoice_Month == "2021-03" and Type == "RECURRING"'
    #categorySummary = pd.pivot_table(forecast, index=["Type", "Category", "Description"],
    #                                 values=["totalAmount"],
    #                                 columns=['IBM_Invoice_Month'],
    #                                 aggfunc={'totalAmount': np.sum}, margins=True, margins_name="Total", fill_value=0)
    #categorySummary.to_excel(writer, 'RecurringForecast')
    #worksheet = writer.sheets['RecurringForecast']
    #format1 = workbook.add_format({'num_format': '$#,##0.00'})
    #format2 = workbook.add_format({'align': 'left'})
    #worksheet.set_column("A:A", 40, format2)
    #worksheet.set_column("B:B", 40, format2)
    #worksheet.set_column("C:ZZ", 18, format1)

    #
    # Build a pivot table for Hourly VSI's with totalRecurringCharges
    #
    virtualServers = classicUsage.query('Category == ["Computing Instance"] and Hourly == [True]')
    if len(virtualServers) > 0:
        virtualServerPivot = pd.pivot_table(virtualServers, index=["Description", "OS"],
                                values=["Hours", "totalRecurringCharge"],
                                columns=['IBM_Invoice_Month'],
                                aggfunc={'Description': len, 'Hours': np.sum, 'totalRecurringCharge': np.sum}, fill_value=0).\
                                        rename(columns={"Description": 'qty', 'Hours': 'Total Hours', 'totalRecurringCharge': 'TotalRecurring'})
        virtualServerPivot.to_excel(writer, 'HrlyVirtualServerPivot')
        worksheet = writer.sheets['HrlyVirtualServerPivot']

    #
    # Build a pivot table for Monthly VSI's with totalRecurringCharges
    #
    monthlyVirtualServers = classicUsage.query('Category == ["Computing Instance"] and Hourly == [False]')
    if len(monthlyVirtualServers) > 0:
        virtualServerPivot = pd.pivot_table(monthlyVirtualServers, index=["Description", "OS"],
                                values=["totalRecurringCharge"],
                                columns=['IBM_Invoice_Month'],
                                aggfunc={'Description': len, 'totalRecurringCharge': np.sum}, fill_value=0).\
                                        rename(columns={"Description": 'qty', 'totalRecurringCharge': 'TotalRecurring'})
        virtualServerPivot.to_excel(writer, 'MnthlyVirtualServerPivot')
        worksheet = writer.sheets['MnthlyVirtualServerPivot']


    #
    # Build a pivot table for Hourly Bare Metal with totalRecurringCharges
    #
    bareMetalServers = classicUsage.query('Category == ["Server"]and Hourly == [True]')
    if len(bareMetalServers) > 0:
        bareMetalServerPivot = pd.pivot_table(bareMetalServers, index=["Description", "OS"],
                                values=["Hours", "totalRecurringCharge"],
                                columns=['IBM_Invoice_Month'],
                                aggfunc={'Description': len,  'totalRecurringCharge': np.sum}, fill_value=0).\
                                        rename(columns={"Description": 'qty', 'Hours': np.sum, 'totalRecurringCharge': 'TotalRecurring'})
        bareMetalServerPivot.to_excel(writer, 'HrlyBaremetalServerPivot')
        worksheet = writer.sheets['HrlyBaremetalServerPivot']

    #
    # Build a pivot table for Monthly Bare Metal with totalRecurringCharges
    #
    monthlyBareMetalServers = classicUsage.query('Category == ["Server"] and Hourly == [False]')
    if len(monthlyBareMetalServers) > 0:
        monthlyBareMetalServerPivot = pd.pivot_table(monthlyBareMetalServers, index=["Description", "OS"],
                                values=["totalRecurringCharge"],
                                columns=['IBM_Invoice_Month'],
                                aggfunc={'Description': len,  'totalRecurringCharge': np.sum}, fill_value=0).\
                                        rename(columns={"Description": 'qty', 'totalRecurringCharge': 'TotalRecurring'})
        monthlyBareMetalServerPivot.to_excel(writer, 'MthlyBaremetalServerPivot')
        worksheet = writer.sheets['MthlyBaremetalServerPivot']
        format1 = workbook.add_format({'num_format': '$#,##0.00'})
        format2 = workbook.add_format({'align': 'left'})
        worksheet.set_column("A:A", 40, format2)
        worksheet.set_column("B:B", 40, format2)

  # IF PaaS credential included add usage reports
    if len(paasUsage) >0:
        paasUsage.to_excel(writer, "PaaS_Usage")
        worksheet = writer.sheets['PaaS_Usage']
        format1 = workbook.add_format({'num_format': '$#,##0.00'})
        format2 = workbook.add_format({'align': 'left'})
        worksheet.set_column("A:C", 12, format2)
        worksheet.set_column("D:E", 25, format2)
        worksheet.set_column("F:G", 18, format1)
        worksheet.set_column("H:I", 25, format2)
        worksheet.set_column("J:J", 18, format1)

        paasSummary = pd.pivot_table(paasUsage, index=["resource_name"],
                                        values=["charges"],
                                        columns=["invoiceMonth"],
                                        aggfunc={'charges': np.sum, }, margins=True, margins_name="Total",
                                        fill_value=0)
        paasSummary.to_excel(writer, 'PaaS_Summary')
        worksheet = writer.sheets['PaaS_Summary']
        format1 = workbook.add_format({'num_format': '$#,##0.00'})
        format2 = workbook.add_format({'align': 'left'})
        worksheet.set_column("A:A", 35, format2)
        worksheet.set_column("B:ZZ", 18, format1)

        paasSummaryPlan = pd.pivot_table(paasUsage, index=["resource_name", "plan_name"],
                                     values=["charges"],
                                     columns=["invoiceMonth"],
                                     aggfunc={'charges': np.sum, }, margins=True, margins_name="Total",
                                     fill_value=0)
        paasSummaryPlan.to_excel(writer, 'PaaS_Plan_Summary')
        worksheet = writer.sheets['PaaS_Plan_Summary']
        format1 = workbook.add_format({'num_format': '$#,##0.00'})
        format2 = workbook.add_format({'align': 'left'})
        worksheet.set_column("A:B", 35, format2)
        worksheet.set_column("C:ZZ", 18, format1)

    writer.save()

def getAccountId(IC_API_KEY):
    ##########################################################
    ## Get Account from the passed API Key
    ##########################################################
    error = None
    logging.info("Retrieving IBM Cloud Account ID from ApiKey.")
    try:
        authenticator = IAMAuthenticator(IC_API_KEY)
    except ApiException as e:
        logging.error("API exception {}.".format(str(e)))
        error = ("API exception {}.".format(str(e)))
        return None, error
    try:
        iam_identity_service = IamIdentityV1(authenticator=authenticator)
    except ApiException as e:
        logging.error("API exception {}.".format(str(e)))
        error = ("API exception {}.".format(str(e)))
        return None, error

    try:
        api_key = iam_identity_service.get_api_keys_details(
          iam_api_key=IC_API_KEY
        ).get_result()
    except ApiException as e:
        logging.error("API exception {}.".format(str(e)))
        error = ("API exception {}.".format(str(e)))
        return None, error

    return api_key["account_id"], error

def accountUsage(IC_API_KEY, IC_ACCOUNT_ID, startdate, enddate):
    ##########################################################
    ## Get Usage for Account matching recuring invoice periods
    ##########################################################
    error = None
    accountUsage = pd.DataFrame(columns=['usageMonth',
                               'invoiceMonth',
                               'resource_name',
                               'plan_name',
                               'billable_charges',
                               'non_billable_charges',
                               'unit',
                               'quantity',
                               'charges']
                                )

    try:
        authenticator = IAMAuthenticator(IC_API_KEY)
    except ApiException as e:
        logging.error("API exception {}.".format(str(e)))
        error = ("API exception {}.".format(str(e)))
        return accountUsage, error
    try:
        usage_reports_service = UsageReportsV4(authenticator=authenticator)
    except ApiException as e:
        logging.error("API exception {}.".format(str(e)))
        error = ("API exception {}.".format(str(e)))
        return accountUsage, error

    # PaaS consumption is delayed by one recurring invoice (ie April usage on June 1 recurring invoice)
    paasStart = startdate - relativedelta(months=1)
    paasEnd = enddate - relativedelta(months=2)

    while paasStart <= paasEnd + relativedelta(days=1):
        usageMonth = paasStart.strftime('%Y-%m')
        recurringMonth = paasStart + relativedelta(months=2)
        recurringMonth = recurringMonth.strftime('%Y-%m')
        logging.info("Retrieving PaaS Usage from {}.".format(usageMonth))
        try:
            usage = usage_reports_service.get_account_usage(
                account_id=IC_ACCOUNT_ID,
                billingmonth=usageMonth,
                names=True
            ).get_result()
        except ApiException as e:
            logging.error("API exception {}.".format(str(e)))
            error = ("API exception {}.".format(str(e)))
            return accountUsage(), error
        paasStart += relativedelta(months=1)
        for u in usage['resources']:
            for p in u['plans']:
                for x in p['usage']:
                    row = {
                        'usageMonth': usageMonth,
                        'invoiceMonth': recurringMonth,
                        'resource_name': u['resource_name'],
                        'billable_charges': u["billable_cost"],
                        'non_billable_charges': u["non_billable_cost"],
                        'plan_name': p["plan_name"],
                        'unit': x["unit"],
                        'quantity': x["quantity"],
                        'charges': x["cost"],
                    }
                    accountUsage = accountUsage.append(row, ignore_index=True)
    return accountUsage, error

@celery.task()
def runAnalysis(IC_API_KEY, month, endmonth):
    # Calculate invoice dates based on SLIC invoice cutoffs.
    startdate, enddate = getInvoiceDates(month, endmonth)

    #  Retrieve Invoices from classic
    classicUsage, error = getInvoiceDetail(IC_API_KEY, startdate, enddate)

    if error != None:
        return None, error
    # Retrieve Usage from IBM Cloud
    IC_ACCOUNT_ID, error = getAccountId(IC_API_KEY)
    if error != None:
        return None, error

    paasUsage, error = accountUsage(IC_API_KEY, IC_ACCOUNT_ID, startdate, enddate)
    if error != None:
        return None, error
    # Build Exel Report
    filename = str(uuid.uuid4()) + ".xlsx"
    createReport(filename, classicUsage, paasUsage)
    return filename, error

@app.route('/', methods=['GET', 'POST'])
def index():
    form=InvoiceAnalysisRequest(request.form)
    if request.method == 'POST' and form.validate():
        session["IC_API_KEY"] = request.form.get("ic_api_key")
        session["month"] = request.form.get("month")
        if request.form.get("endmonth") != "":
            session["endmonth"] = request.form.get("endmonth")
        else:
            session["endmonth"] = request.form.get("month")
        return render_template("running.html")
    return render_template("index.html", form=form)

@app.route('/runreport', methods=['POST'])
def runreport():
    reportAnalysis=runAnalysis.delay(session.get("IC_API_KEY", None), session.get("month", None), session.get("endmonth", None))
    response = jsonify()
    response.status_code=202
    response.headers['taskid'] = reportAnalysis
    return response

@app.route("/reportstatus/<task_id>", methods=["GET"])
def reportstatus(task_id):
    results = runAnalysis.AsyncResult(task_id)
    logging.info(results)
    if results.successful():
        filename, error = results.get()
        if error == None:
            content = render_template('finished.html')
            session['filename'] = filename
            status = "complete"
        else:
            content = render_template('error.html', error=error)
            status = "failed"
        return jsonify({'task_id': task_id, 'status': status, 'content': content})
    elif results.failed():
            content = render_template('error.html', error="Unknown Error")
            status = "failed"
            return jsonify({'task_id': task_id, 'status': status, 'content': content})
    else:
            status = "inprocess"
    return jsonify({'task_id': task_id, 'status': status})


@app.route('/download')
def download_file():
    filename = session.get('filename')
    if os.path.exists(filename):
        file_handle = open(filename, 'r')
    else:
        return render_template("downloaderror.html")
    @after_this_request
    def remove_file(response):
        try:
            os.remove(filename)
            file_handle.close()
        except Exception as error:
            logging.error("Error removing or closing downloaded file handle", error)
        return response
    return send_file(filename, attachment_filename="invoiceAnalysis.xlsx", as_attachment=True)

setup_logging()
if __name__ == "__main__":
    app.run(host='0.0.0.0')
