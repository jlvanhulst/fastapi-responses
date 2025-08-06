"""
(C) 2025 Jean-Luc Vanhulst - Valor Ventures
MIT License

This file contains tool call function examples that can be used by the prompt system.

"""
import httpx
import html2text
from pydantic import BaseModel, HttpUrl, Field
import logging
import markdown
import random
from typing import List

logger = logging.getLogger(__name__)


def markdown_to_html(md_text):
    """
    This helper function is used to convert markdown to html.
    It converts the markdown to html and returns the html.
    Handy for AI prompt output that is markdown formatted.

    Args:
        md_text (str): The markdown text to convert to html.

    Returns:
        str: The html content of the markdown text.
    """
    return markdown.markdown(md_text)


class WebScrapeParameters(BaseModel):
    url: HttpUrl = Field(..., description="The URL of the website to scrape")
    ignore_links: bool = Field(False, description="Ignore links in the text. Use 'False' to receive the URLs of nested pages to scrape.")
    max_length: int = Field(None, description="Maximum length of the text to return")


def html_to_text(html, ignore_links=False, bypass_tables=False, ignore_images=True):
    """
    This function is used to convert html to text.
    It converts the html to text and returns the text.

    Args:
        html (str): The HTML content to convert to text.
        ignore_links (bool): Ignore links in the text. Use 'False' to receive the URLs of nested pages to scrape.
        bypass_tables (bool): Bypass tables in the text. Use 'False' to receive the text of the tables.
        ignore_images (bool): Ignore images in the text. Use 'False' to receive the text of the images.

    Returns:
        str: The text content of the webpage. If max_length is provided, the text will be truncated to the specified length.
    """
    text = html2text.HTML2Text()
    text.ignore_links = ignore_links
    text.bypass_tables = bypass_tables
    text.ignore_images = ignore_images
    return text.handle(html)


async def webscrape(info: WebScrapeParameters):
    """
    This function is used to scrape a webpage.
    It converts the html to text and returns the text.

    Args:
        info (WebScrapeParameters): The parameters for the web scrape.

    Returns:
        str: The text content of the webpage. If max_length is provided, the text will be truncated to the specified length.
    """
    header = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36'}
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(str(info.url), headers=header, timeout=5)
    except Exception as e:
        logging.error(f"Failed to fetch URL {info.url}: {e}")
        return f"Error fetching the url {info.url} - {e}"

    logging.info(f"Successful webscrape {info.url} {response.status_code}")
    out = html_to_text(response.text, ignore_links=info.ignore_links)

    if info.max_length:
        return out[0:info.max_length]
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
