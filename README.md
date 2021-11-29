# IBM Cloud Classic Infrastructure Invoice Analysis Report
*invoiceAnalysis.py* collects IBM Cloud Classic Infrastructure NEW, RECURRING, and CREDIT invoices and PaaS Usage between months specified in the parameters consolidates the data into an Excel worksheet for billing and usage analysis. 
In addition to consolidation of the detailed data,  pivot tables are created in Excel tabs to assist with understanding account usage.

This implementation is based on [invoiceAnalysis](https://github.com/jonghall/invoiceAnalysis) and is example Web Application written in Python Flask which can be hosted in IBM Code Engine as a Application.
After collecting the invoices and creating the file the user is prompted to download the Excel file created.

Script | Description
------ | -----------
invoiceAnalysis.py | Analyzes all invoices between two dates and creates excel reports.
requirements.txt | Package requirements
logging.json | LOGGER config used by script
Dockerfile | Docker Build file used by code engine to build container.
uwsgi.ini | uWSGI server configuration

### Identity & Access Management Requirements
| APIKEY | Description | Min Access Permissions
| ------ | ----------- | ----------------------
| IBM Cloud API Key | API Key used to pull classic and PaaS invoices and Usage Reports. | IAM Billing Viewer Role


### Output Description
One Excel worksheet is created with multiple tabs from the collected data (Classic Invoices & PaaS Usage between start and end month specified).   _Tabs are only be created if there are related resources on the collected invoices._

*Excel Tab Explanation*
   - ***Detail*** tab has every invoice item for all the collected invoices represented as one row each. For invoices with multiple items, each row represents one top level invoice item.  All invoice types are included, including CREDIT invoices.  The detail tab can be sorted or filtered to find specific dates, billing item id's, or specific services.  
   - ***TopSheet-YYYY-MM*** tab(s) map each portal invoice to their corresponding IBM CFTS invoice(s) they are billed on.  These tabs can be used to facilitate reconciliation.
   - ***InvoiceSummary*** tab is a pivot table of all the charges by product category & month by invoice type. This tab can be used to understand changes in month to month usage.
   - ***CategorySummary*** tab is a pivot of all recurring charges broken down by Category and sub category (for example specific VSI sizes or Bare metal server types) to dig deeper into month to month usage changes.
   - ***HrlyVirtualServerPivot*** tab is a pivot of just Hourly Classic VSI's if they exist
   - ***MnthlyVirtualServerPivot*** tab is a pivot of just monthly Classic VSI's if they exist
   - ***HrlyBareMetalServerPivot*** tab is a pivot of Hourly Bare Metal Servers if they exist
   - ***MnthlyBareMetalServerPivot*** tab is a pivot table of monthly Bare Metal Server if they exist
   - ***PaaS_Usage*** shows the complete list of PaaS Usage showing the usageMonth, InvoiceMonth, ServiceName, and Plan Name with billable charges for each unit associated with the service. 
   - ***PaaS_Summary*** shows the invoice charges for each PaaS service consumed.  Note the columns represent CFTS invoice month, not actual usage month.
   - ***PaaS_Plan_Summary*** show an additional level of detail for each PaaS service and plan consumed.  Note the columns represent CFTS invoice month, not actual usage month/

### Setting up IBM Code Engine and building container to start the Web Application
1. Create an instance of a Redis Database.  Minimum defaults are adequate.  Version 5 of REDIS should be chosen.  The redis instances is used by the Web Application to manage background tasks. 
2. Create project and build the application.  
   2.1. Open the Code Engine console  
   2.2. Select Start creating from Start from source code. 
   2.3. Select Application  
   2.4. Enter a name for the application such as invoiceanalysis. Use a name for your job that is unique within the project.  
   2.5. Select a project from the list of available projects of if this is the first one, create a new one. Note that you must have a selected project to deploy an app.  
   2.6. Enter the URL for this GitHub repository and click specify build details.   Click Next.  
   2.7. Select Dockerfile for Strategy, Dockerfile for Dockerfile, 10m for Timeout, and Medium for Build resources. Click Next.  
   2.8. Select a container registry location, such as IBM Registry, Dallas.  
   2.9. Select Automatic for Registry access.  
   2.10. Select an existing namespace or enter a name for a new one, for example, newnamespace.  
   2.11. Enter a name for your image and optionally a tag.  
   2.12. Click Done.  
   2.13. Click Create.
3. Establish a service Binding between the Code Engine application and the created Redis Database.  (per these instructions [Instructions](https://cloud.ibm.com/docs/codeengine?topic=codeengine-service-binding))
4. Logging for job can be found from application screen, by clicking Actions, Logging
