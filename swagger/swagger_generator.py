import ast
import importlib.util
import inspect
import json
import os

import frappe
from pydantic import BaseModel



def get_default_params(func):
    return []



def get_request_body(fun):
    data = {}
    params = get_function_params(fun)
    for i in params :
        data[i.get("name")] = {"type": i.get("schema").get("type")}
    return data
    # return  {  "name": {"type": "string",
    #                    "description": "A required string field."                                                              } 
    # }  
                                                              
                                                          

    pass
def find_pydantic_model_in_decorator(node):
    """Find the name of the Pydantic model used in the validate_request decorator.
    
    Args:
        node (ast.AST): The AST node representing the function definition.
    
    Returns:
        str: The name of the Pydantic model used in the decorator, if found.
    """
    for n in ast.walk(node):
        if isinstance(n, ast.FunctionDef):
            for decorator in n.decorator_list:
                if isinstance(decorator, ast.Call):
                    if (
                        isinstance(decorator.func, ast.Name)
                        and decorator.func.id == "validate_request"
                    ):
                        if decorator.args:
                            if isinstance(decorator.args[0], ast.Name):
                                return decorator.args[0].id
                            elif isinstance(decorator.args[0], ast.Attribute):
                                return f"{ast.dump(decorator.args[0].value)}.{decorator.args[0].attr}"
    return None


def get_pydantic_model_schema(model_name, module):
    """Extract the schema from a Pydantic model.
    
    Args:
        model_name (str): The name of the Pydantic model.
        module (module): The module where the model is defined.
    
    Returns:
        dict: The JSON schema of the Pydantic model, if valid.
    """
    if hasattr(module, model_name):
        model = getattr(module, model_name)
        if issubclass(model, BaseModel):
            return model.model_json_schema()
    return None
def parse_docstring(docstring: str) -> dict:

    # params = {}
    params_list =[]
    # Split the docstring into lines and strip whitespace
    lines = [line.strip() for line in docstring.splitlines()]
    reading_params = False
    for line in lines:
        params ={}
        # Look for the start of the params section (you might also check for "params:" if that's what you use)
        if  line.find("params") != -1:
            reading_params = True
            continue
        # Once in the params section, process lines that contain ":"
        if reading_params:
            # Skip empty lines
            if not line:
                continue
            # Stop processing if we hit a line that doesn't seem to define a parameter
            if ":" not in line:
                break
            key, type_str = line.split(":", 1)
            tp = type_str.split(" ")
            tp = [ i for i in tp if len(i) > 1 ]
            params["name"]  = key.strip()
            params["required"] =tp[1] == "Required"
            params["schema"] = {"type": tp[0].lower()}
            
            params_list.append(params)
            # params[key.strip()] = type_str.strip()
    return params_list
def get_function_params(func) -> dict:
    # Get a clean version of the docstring
    docstring = inspect.getdoc(func)
    if not docstring:
        return {}
    return parse_docstring(docstring)
def process_function(app_name, module_name, func_name, func, swagger, module):
    """Process each function to update the Swagger paths.
    
    Args:
        app_name (str): The name of the app.
        module_name (str): The name of the module.
        func_name (str): The name of the function being processed.
        func (function): The function object.
        swagger (dict): The Swagger specification to be updated.
        module (module): The module where the function is defined.
    """
    try:
        source_code = inspect.getsource(func)
        
        tree = ast.parse(source_code)

        # Skip functions that do not contain validate_http_method calls
        if not any(
            "validate_http_method" in ast.dump(node) and isinstance(node, ast.Call)
            for node in ast.walk(tree)
        ):
            print(f"Skipping {func_name}: 'validate_http_method' not found")
            #return

        # Find the Pydantic model used in the validate_request decorator
        pydantic_model_name = find_pydantic_model_in_decorator(tree)

        # Construct the API path for the function
        path = f"/api/method/{app_name}.api.{module_name}.{func_name}".lower()

        # Define the mapping of HTTP methods to check for in the source code
        http_methods = {
            "GET": "GET",
            "POST": "POST",
            "PUT": "PUT",
            "DELETE": "DELETE",
            "PATCH": "PATCH",
            "OPTIONS": "OPTIONS",
            "HEAD": "HEAD",
        }
        params_dtealis_list = []
        # Default HTTP method is POST
     
        documentation = func.__doc__
        # if documentation:
        # params_list = get_function_params(func)
        # frappe.throw(str(func_name))

        params =[]
        http_method = "POST"
        for method in http_methods:
            if method in source_code:
                http_method = method
                break

        # Define the request body for methods that modify data
        request_body = {}
        if  http_method in ["POST", "PUT", "PATCH"]:
            # frappe.throw("POST")
            # pydantic_schema =   get_pydantic_model_schema(pydantic_model_name, module)
            pydantic_schema  = get_request_body(func)
            if pydantic_schema :
                request_body = {
                        "description": "Request body",
                        "required": True,
                        "content": {"application/json": {"schema":
                                                        {
                                                                "type": "object",
                                                                "properties": pydantic_schema
                                                        }}},
                    }

        # Define query parameters for methods that retrieve data
        
        if http_method in ["GET", "DELETE", "OPTIONS", "HEAD"]:
            signature = inspect.signature(func)

            
            # frappe.throw(str(signature))
            for param_name, param in signature.parameters.items():
                if (
                    param.default is inspect.Parameter.empty
                    and not "kwargs" in param_name and not "args" in param_name
                ):
                    param_type = "string"
                    params.append(
                        {
                            "name": param_name,
                            "in": "query",
                            "required": True,
                            "schema": {"type": param_type},
                        }
                    )
                for obj_type in ["page_size" , "page_number"]:
                        param_type = "integer"
                        params.append(
                            {
                                "name": obj_type,
                                "in": "query",
                                "required": False,
                                "schema": {"type": param_type},
                            }
                        )
        # Define the response schema
        responses = {
            "200": {
                "description": "Successful response",
                "content": {"application/json": {"schema": {"type": "object"}}},
            }
        }

        # Assign tags for the Swagger documentation
        tags = [module_name]

        # Initialize the path if not already present
        if path not in swagger["paths"]:
            swagger["paths"][path] = {}
        # frappe.throw(str(request_body))
        # Update the Swagger specification with the function details
        swagger["paths"][path][http_method.lower()] = {
            "summary": func_name.title().replace("_", " "),
            "tags": tags,
            "parameters": params,
            "requestBody": request_body if request_body else None,
            "responses": responses,
            "security": [{"basicAuth": []}],
        }
    except Exception as e:
        # Log any errors that occur during processing
        frappe.log_error(
            f"Error processing function {func_name} in module {module_name}: {str(e)}"
        )


def load_module_from_file(file_path):
    """Load a module dynamically from a given file path.
    
    Args:
        file_path (str): The file path of the module.
    
    Returns:
        module: The loaded module.
    """
    module_name = os.path.basename(file_path).replace(".py", "")
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@frappe.whitelist(allow_guest=True)
def generate_swagger_json():
    """Generate Swagger JSON documentation for all API methods.
    
    This function processes all Python files in the `api` directories of installed apps
    to generate a Swagger JSON file that describes the API methods.
    """
    swagger_settings = frappe.get_single("Swagger Settings")
    
    # Initialize the Swagger specification
    swagger = {
        "openapi": "3.0.0",
        "info": {
            "title": f"{swagger_settings.app_name} API",
            "version": "1.0.0",
        },
        "paths": {},
        "components": {},
    }

    # Add security schemes based on the settings in "Swagger Settings"
    if swagger_settings.token_based_basicauth or swagger_settings.bearerauth:
        swagger["components"]["securitySchemes"] = {}
        swagger["security"] = []

    if swagger_settings.token_based_basicauth:
        swagger["components"]["securitySchemes"]["basicAuth"] = {
            "type": "http",
            "scheme": "basic",
        }
        swagger["security"].append({"basicAuth": []})

    if swagger_settings.bearerauth:
        swagger["components"]["securitySchemes"]["bearerAuth"] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
        swagger["security"].append({"bearerAuth": []})

    # Get the path to the Frappe bench directory
    frappe_bench_dir = frappe.utils.get_bench_path()
    file_paths = []

    # Gather all Python files in the `api` folders of each installed app
    """
    for app in frappe.get_installed_apps():
        try:
            api_dir = os.path.join(frappe_bench_dir, "apps", app, app, "api")
            
            # Check if the `api` directory exists
            if os.path.exists(api_dir) and os.path.isdir(api_dir):
                # Walk through the `api` directory to gather all `.py` files
                for root, dirs, files in os.walk(api_dir):
                    for file in files:
                        if file.endswith(".py"):
                            file_paths.append((app,os.path.join(root, file)))
        except Exception as e:
            # Log any errors encountered while processing the app
            frappe.log_error(f"Error processing app '{app}': {str(e)}")
            continue"
    """
    app = swagger_settings.app_name
    api_dir = os.path.join(frappe_bench_dir, "apps", app, app, "api")
    #frappe.throw(str(os.listdir(api_dir) ))
    # Check if the `api` directory exists
    if os.path.exists(api_dir) and os.path.isdir(api_dir):
        # Walk through the `api` directory to gather all `.py` files
        
        files = [f for f in os.listdir(api_dir) if os.path.isfile(api_dir +"/"+f)] 
        root = api_dir
        for f in files :
            if f.endswith(".py"):
                file_paths.append((app,os.path.join(root, f)))
    else:   
         pass
    for app,file_path in file_paths:
        try:
            if os.path.isfile(file_path) and app in str(file_path):
                module = load_module_from_file(file_path)
                module_name = os.path.basename(file_path).replace(".py", "")
                for func_name, func in inspect.getmembers(module, inspect.isfunction):
                    if func_name in ["get_all", "get", "edit", "submit" ,
                                     "login" ,"logout" ,"refresh_token"]:
                        process_function(app, module_name, func_name, func, swagger, module)
            else:
                print(f"File not found: {file_path}")
        except Exception as e:
            frappe.log_error(f"Error loading or processing file {file_path}: {str(e)}")

    # Define the path to the Swagger JSON file
    www_dir = os.path.join(frappe_bench_dir, "apps", "swagger", "swagger", "www")

    # Ensure the www directory exists
    if not os.path.exists(www_dir):
        os.makedirs(www_dir)

    # Save the generated Swagger JSON to a file
    file_path = os.path.join(www_dir, "swagger.json")
    with open(file_path, "w") as swagger_file:
        json.dump(swagger, swagger_file, indent=4)

    frappe.msgprint("Swagger JSON generated successfully.")