import azure.functions as func
import json
from validation import Validation
from sql_data_fetcher import SqlDataFetcher, QueryParameters
import logging

# Set up logging configuration
logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

# Define the connection string
connection_string = (
    "DRIVER={ODBC Driver 18 for SQL Server};"
    "Server=tcp:synw-smb-sfda-dev-ondemand.sql.azuresynapse.net,1433;"
    "DATABASE=smbuat;"
    "UID=funcuser;"
    "PWD=Smuser@098!!!;"
    "Encrypt=yes;"
    "TrustServerCertificate=no;"
    "Connection Timeout=30;"
)

data_fetcher = SqlDataFetcher(connection_string)

# FunctionApp initialization without authentication
app = func.FunctionApp()



def log_error_and_return_response(error_message, status_code):
    log.error(error_message)
    return func.HttpResponse(
        json.dumps({"message": error_message}),
        mimetype="application/json",
        status_code=status_code
    )
def validate_query_params(validator):
    validation_results = {key: validator_func() for key, validator_func in {
        "account_id": validator.validate_account_id,
        "object_name": validator.validate_object_name,
        "date_range": validator.validate_date_range,
        "page_number": validator.validate_page_number,
        "page_size": validator.validate_page_size
    }.items()}

    errors = {key: value[1] for key, value in validation_results.items() if not value[0]}
    return errors if errors else None


def execute_query(query_params, query_type):
    try:
        query_params_data = query_params.transform()

        if query_type == 'COUNT':
            flag, count_result = data_fetcher.execute_count_query(query_params_data)

            if count_result == 0:
                return {"IsPresent": False}, count_result, 400
            else:
                return {"IsPresent": True}, count_result, 200

        elif query_type == 'DATA':
            json_data = data_fetcher.execute_data_query(query_params_data, flag=0)
            if not json_data:
                return {"message": "NO Data found."}, 400
            else:
                return json_data, 200

        else:
            return log_error_and_return_response("Invalid 'Type' parameter. Valid values are 'COUNT' or 'DATA'.", 400)

    except Exception as ex:
        error_message = f"Error in execute_query: {str(ex)}"
        log.error(error_message)
        raise Exception(error_message)

@app.route(route="SM_AZURE_QUERY")
def http_trigger(req: func.HttpRequest) -> func.HttpResponse:
    try:
        account_id = req.params.get('Account_Id')
        if not account_id:
            return log_error_and_return_response("Account_Id is required.", 400)

        # Retrieve the 'Type' parameter from the request
        query_type = req.params.get('Type', None)

        # Check if 'Type' is not provided or invalid
        if query_type not in ['COUNT', 'DATA'] and req.params.get('Object_Name', None):
            return log_error_and_return_response("Invalid or missing 'Type' parameter. Valid values are 'COUNT' or 'DATA'.", 400)

        query_params = QueryParameters(
            account_id=account_id,
            object_name=req.params.get('Object_Name', None),
            date_start_daymonthyear=req.params.get('Date_Start_YearMonthDay', '*'),
            date_end_daymonthyear=req.params.get('Date_End_YearMonthDay', '*'),
            page_number=int(req.params.get('Page_Number', 0)),
            page_size=int(req.params.get('Page_Size', 10))
        )
        validator = Validation(query_params)

        if not query_params.object_name or query_params.object_name.lower() == None:
            query_params.object_name = query_params.object_name or "Service_Work_Order__c"
            query_type = 'COUNT'
            result, count_result, status = execute_query(query_params, 'COUNT')
        else:

            validation_result = validate_query_params(validator)
            if validation_result:
                return log_error_and_return_response(f"Validation failed: {validation_result}", 400)

            if query_type == 'COUNT':
                result, count_result, status = execute_query(query_params, 'COUNT')
            elif query_type == 'DATA':
                result, status = execute_query(query_params, 'DATA')

        query_result = {
            "Account_Id": query_params.account_id,
            "Object_Name": query_params.object_name,
            "Date_Start_YearMonthDay": query_params.date_start_daymonthyear,
            "Date_End_YearMonthDay": query_params.date_end_daymonthyear,
            "Page_Number": query_params.page_number,
            "Page_Size": query_params.page_size,
            "Data": result
        }

        if query_type == 'COUNT':
            query_result["Count"] = count_result

        return func.HttpResponse(json.dumps(query_result), mimetype="application/json", status_code=status)

    except ValueError as ve:
        return log_error_and_return_response(f"Validation error: {ve}", 400)

    except Exception as e:
        return log_error_and_return_response(f"An unexpected error occurred: {str(e)}", 500)