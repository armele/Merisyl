import os
import requests
import argparse
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def setup_selenium():
    """Sets up the Selenium WebDriver with Chrome."""
    options = Options()
    options.add_argument("--headless")  # Run in headless mode
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    service = Service("./chromedriver.exe")  # Update with your chromedriver path
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def fetch_page_content(url, driver):
    """Fetches the page content using Selenium."""
    driver.get(url)
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        return driver.page_source
    except Exception as e:
        print(f"Error loading page {url}: {e}")
        return None

def save_html(content, filename):
    """Saves the HTML content to a file."""
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)

def crawl(url, parent, base_domain, visited, output_dir, log_file, link_file, driver, verbose):
    """Recursively crawls links within the same domain and logs output."""
    if url in visited:
        if verbose:
            log_file.write(f"Skipping: {url} from {parent}\n")
        return

    # This is output even if not verbose, to provide an indication of progress.
    log_file.write(f"Crawling: {url} from {parent}\n")
    
    try:
        # Fetch content using Selenium
        page_content = fetch_page_content(url, driver)
        if not page_content:
            log_file.write(f"Failed to fetch: {url}\n")
            return

        # Save the HTML content
        url_path = urlparse(url).path.strip("/")
        filename = os.path.join(output_dir, f"{url_path.replace('/', '_') or 'index'}.html")
        if urlparse(url).query:  # Handle query parameters
            query_part = urlparse(url).query.replace('&', '_').replace('=', '-')
            filename = filename.replace(".html", f"_{query_part}.html")
        
        save_html(page_content, filename)

        # Mark as visited
        visited.add(url)

        # Parse and find new links
        soup = BeautifulSoup(page_content, "html.parser")
        for link in soup.find_all("a"):
            if verbose:
                log_file.write(f"Full link tag: {link}\n")
                log_file.write(f"Attributes of link: {link.attrs}\n")           
            
            # Extract href attribute
            raw_href = link.attrs.get("href", "").strip()
            
            if not raw_href:
                if verbose:
                    log_file.write(f"Skipping link without href: {link}\n")
                continue

            if verbose:
                # Log the found link and its resolved URL
                log_file.write(f"Extracted (raw) href: {raw_href}\n") 
            
            # If href is already a full URL, use it directly
            if raw_href.startswith("http://") or raw_href.startswith("https://"):
                new_url = raw_href
            else:
                # Resolve relative URL using urljoin
                new_url = urljoin(url, raw_href)

            # Normalize the URL to avoid duplicates (e.g., "https://example.com/foo" vs "https://example.com/foo/")
            new_url = new_url.rstrip("/")

            if verbose:
                log_file.write(f"Resolved URL: {new_url}\n")
            
            if "atlassian" in new_url.lower():
                link_file.write(f"On page {url}: Outdated link '{link.get_text()}' identified: {new_url}\n")
            
            parsed_new_url = urlparse(new_url)

            # Skip if not within the same domain
            if parsed_new_url.netloc != base_domain:
                continue

            # Add to crawl queue if not visited
            if new_url not in visited:
                crawl(new_url, url, base_domain, visited, output_dir, log_file, link_file, driver, verbose)

    except Exception as e:
        print(f"Error crawling {url}: {e}\n")

def main(verbose):
    start_url = input("Enter the website homepage URL: ").strip()
    parsed_start = urlparse(start_url)
    base_domain = parsed_start.netloc

    if not base_domain:
        print("Invalid URL. Please provide a full URL (e.g., https://example.com).")
        return
    
    output_dir = "crawled_pages"
    os.makedirs(output_dir, exist_ok=True)
    
    visited = set()
    
    # Setup Selenium driver
    driver = setup_selenium()
    
    with open("output.log", "w", encoding="utf-8") as log_file, \
        open("link.log", "w", encoding="utf-8") as link_file:
        try:
            crawl(start_url, "Root", base_domain, visited, output_dir, log_file, link_file, driver, verbose)
        finally:
            driver.quit()  # Ensure the driver is properly closed

# Usage example
if __name__ == "__main__":
    # Set up argument parsing
    parser = argparse.ArgumentParser(description='Crawl a website and save its HTML.')
    parser.add_argument("--verbose", help="increase output verbosity", action="store_true")
    parser.set_defaults(verbose=False)
    
    # Parse arguments
    args = parser.parse_args()
    
    main(args.verbose)
