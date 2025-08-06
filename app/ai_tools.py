import importlib
import inspect
import logging
import os
from typing import Any, Callable, ClassVar, Dict, Optional

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


class JsonResponse(BaseModel):
    """Base class for all JSON responses in the system."""
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", arbitrary_types_allowed=True)


_tool_dict: Dict[str, Dict[str, Any]] = {
    "webscrape": {
        "module": "ai_tools",
    },
}


def register_tools(function_name: str, module: str = None, function: Callable = None):
    """
    Register a single tool in the tool_dict.

    Args:
        function_name (str): The name of the function to register (mandatory)
        module (str): Module name to import the function from (optional)
        function (callable): Direct function object to register (optional)

    Either module or function must be provided, but not both.

    Examples:
        register_tools("some_function", module="my_module")
        register_tools("some_function", function=some_function_object)
    """
    if module is None and function is None:
        raise ValueError("Either 'module' or 'function' parameter must be provided")
    if module is not None and function is not None:
        raise ValueError("Cannot provide both 'module' and 'function' parameters")

    _tool_dict[function_name] = {
        "module": module,
        "function": function,  # Cache the function object if provided
    }


def get_registered_tools():
    """Get a copy of the registered tools dictionary"""
    return _tool_dict.copy()


class FunctionRequest(BaseModel):
    function: str  # Function name can include module name like module:function
    params: Dict[str, Any]  # parameters for the function as defined in the schema of the function
    user: Optional[str] = None  # user email address, used for ownership of the function call.

    model_config = ConfigDict(extra="ignore")


def _getf(functionName) -> object:
    """get a callable function from a function name with caching"""
    try:
        tool_info = _tool_dict.get(functionName)
        if not tool_info:
            raise Exception(f"Function name '{functionName}' not defined in _tool_dict.")

        if tool_info.get("function") is not None:
            return tool_info["function"]

        module_name = tool_info["module"]
        if not module_name:
            raise Exception(f"No module specified for function '{functionName}'")

        if __package__:
            module = importlib.import_module(f"{__package__}.{module_name}")
        else:
            module = importlib.import_module(module_name)
        func = getattr(module, functionName, None)

        if not func:
            if os.getenv("DEBUG"):
                raise Exception(
                    f"Function '{functionName}' could not be found in module '{module_name}'."
                )
            else:
                return None

        tool_info["function"] = func
        return func
    except Exception as e:
        raise Exception(f"Function name {functionName} not defined - {e}")


async def handle_openai_function(data: FunctionRequest, schema: bool = False):
    """
    Handle an OpenAI function call with optional Pydantic schema validation or schema output.
    This function is intended to be called internally rather than directly via an HTTP request.

    Args:
        data (FunctionRequest): The function call data.
        schema (bool): Flag to determine if schema should be returned.

    Returns:
        Either a dictionary containing the function execution result or the function schema.
    """
    function_name = data.function
    params = data.params or {}
    user = data.user
    tool_info = _tool_dict.get(function_name, {})

    if not tool_info:
        raise Exception(f"Function '{function_name}' is not recognized.")

    pydantic_schema = None
    parameter_class = None  # Pydantic model class for schema validation
    func = _getf(function_name)
    if not func:
        raise Exception(f"Function '{function_name}' could not be retrieved.")
    signature = inspect.signature(func)
    parameter = next(iter(signature.parameters.values()), None)  # Get the first parameter
    if (
        parameter
        and parameter.annotation
        and inspect.isclass(parameter.annotation)
        and issubclass(parameter.annotation, BaseModel)
    ):
        parameter_class = parameter.annotation
    if schema:
        if not parameter_class:
            raise Exception(f"No Pydantic schema defined for function '{function_name}'.")
        pydantic_schema = parameter_class.model_json_schema()
        description = func.__doc__.strip() if func.__doc__ else ""
        openai_function_schema = {
            "type": "function",
            "name": function_name,
            "description": description,
            "strict": False,
            "parameters": pydantic_schema,
        }
        return openai_function_schema
    if user and "email" not in params:
        params["email"] = user

    try:
        if parameter_class:
            validated_params = parameter_class(**params)
            result = await func(validated_params)
        else:
            result = await func(params)
    except TypeError as e:
        raise Exception(f"Invalid parameters for function '{function_name}': {str(e)}")
    except ValueError as e:
        raise Exception(f"Validation error for function '{function_name}': {str(e)}")
    except Exception as e:
        raise Exception(f"Error executing function '{function_name}': {str(e)}")
    return result
