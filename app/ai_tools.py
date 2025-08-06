import importlib
import inspect
import logging
import os
import random
from typing import Any, Callable, ClassVar, Dict, Optional, List

import html2text
import httpx
import markdown
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

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


def frommarkdown(
    text: Optional[str],
    replaceThis: Optional[str] = None,
    withThis: Optional[str] = None,
) -> Optional[str]:
    if text is None:
        return None
    """
    This function is used to convert markdown to html.

    params:
        text: The markdown text to convert to html.
        replaceThis: The text to replace in the html.
        withThis: The text to replace replaceThis with.

    returns:
        The html text.
    """
    extension_configs = {
        "markdown_link_attr_modifier": {
            "new_tab": "on",
            "no_referrer": "external_only",
            "auto_title": "on",
        }
    }
    result = markdown.markdown(
        text,
        extensions=["tables", "markdown_link_attr_modifier"],
        extension_configs=extension_configs,
    )
    if replaceThis is not None and withThis is not None:
        result = result.replace(replaceThis, withThis)
    return result


def html_to_text(html, ignore_links=False, bypass_tables=False, ignore_images=True):
    """
    This function is used to convert html to text.
    It converts the html to text and returns the text.

    Args:
        html (str): The HTML content to convert to text.
        ignore_links (bool): Ignore links in the text. Use 'False' to receive URLs of nested pages.
        bypass_tables (bool): Bypass tables in the text. Use 'False' to receive table text.
        ignore_images (bool): Ignore images in the text. Use 'False' to receive image text.
    Returns:
        str: The text content of the webpage. If max_length is provided, text will be truncated.
    """
    text = html2text.HTML2Text()
    text.ignore_links = ignore_links
    text.bypass_tables = bypass_tables
    text.ignore_images = ignore_images
    return text.handle(
        html,
    )


class WebScrapeParameters(BaseModel):
    url: HttpUrl = Field(..., description="The URL of the website to scrape")
    ignore_links: bool = Field(
        False,
        description="Ignore links in the text. Use 'False' to receive the URLs of nested pages "
        "to scrape.",
    )
    max_length: int = Field(None, description="Maximum length of the text to return")


async def webscrape(info: WebScrapeParameters):
    """
    This function is used to scrape a webpage.
    It converts the html to text and returns the text.

    Args:
        plain_json (dict): The JSON data containing the URL to scrape. It is meant to be called as a
            tool call from a prompt. The json should be in the format of
            {"url": "https://www.example.com", "ignore_links": False, "max_length": 1000}

    Returns:
        str: The text content of the webpage. If max_length is provided, text will be truncated.
    """

    header = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36"
    }
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(str(info.url), headers=header, timeout=5)
    except Exception as e:
        logging.error(f"Failed to fetch URL {info.url}: {e}")
        return f"Error fetching the url {info.url} - {e}"
    logging.info("succesful webscrape " + str(info.url) + " " + str(response.status_code))
    out = html_to_text(response.text, ignore_links=info.ignore_links)
    if info.max_length:
        return out[0 : info.max_length]
    else:
        return out


class RevenueDataRequest(BaseModel):
    """Request model for generating client revenue data."""
    client_name: str = Field(..., description="The name of the client")
    year: int = Field(..., description="The year for which to generate revenue data", ge=2020, le=2030)


class MonthlyRevenue(BaseModel):
    """Monthly revenue data point."""
    month: int = Field(..., description="Month number (1-12)", ge=1, le=12)
    month_name: str = Field(..., description="Month name (January, February, etc.)")
    revenue: float = Field(..., description="Revenue amount in USD")


class RevenueDataResponse(BaseModel):
    """Response model for client revenue data."""
    client_name: str = Field(..., description="The client name")
    year: int = Field(..., description="The year")
    total_revenue: float = Field(..., description="Total annual revenue")
    average_monthly_revenue: float = Field(..., description="Average monthly revenue")
    monthly_data: List[MonthlyRevenue] = Field(..., description="Monthly revenue breakdown")


async def generate_client_revenue_data(request: RevenueDataRequest) -> RevenueDataResponse:
    """
    Generate mock client revenue data for demonstration purposes.
    
    Creates 12 months of revenue data starting with a random base amount (1-10 million)
    and then varying each subsequent month by +/- 50% of the previous month.
    
    Args:
        request: RevenueDataRequest containing client_name and year
        
    Returns:
        RevenueDataResponse with monthly revenue breakdown and summary statistics
        
    Example:
        request = RevenueDataRequest(client_name="Acme Corp", year=2024)
        result = await generate_client_revenue_data(request)
    """
    month_names = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]
    
    # Start with a random base revenue between 1-10 million
    base_revenue = random.uniform(1_000_000, 10_000_000)
    
    monthly_data = []
    current_revenue = base_revenue
    
    for month in range(1, 13):
        # For the first month, use the base revenue
        if month == 1:
            revenue = base_revenue
        else:
            # Vary by +/- 50% of the previous month
            variation = random.uniform(-0.5, 0.5)
            revenue = current_revenue * (1 + variation)
            # Ensure revenue doesn't go negative
            revenue = max(revenue, 100_000)
        
        monthly_data.append(MonthlyRevenue(
            month=month,
            month_name=month_names[month - 1],
            revenue=round(revenue, 2)
        ))
        
        current_revenue = revenue
    
    # Calculate summary statistics
    total_revenue = sum(data.revenue for data in monthly_data)
    average_monthly_revenue = total_revenue / 12
    
    return RevenueDataResponse(
        client_name=request.client_name,
        year=request.year,
        total_revenue=round(total_revenue, 2),
        average_monthly_revenue=round(average_monthly_revenue, 2),
        monthly_data=monthly_data
    )
