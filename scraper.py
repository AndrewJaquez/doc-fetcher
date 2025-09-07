#!/usr/bin/env python3

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
import sys
from collections import deque

class DocScraper:
    def __init__(self, base_url, output_file="output.txt"):
        self.base_url = base_url
        self.output_file = output_file
        self.visited_urls = set()
        self.scraped_content = []
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
    
    def is_valid_docs_url(self, url):
        parsed = urlparse(url)
        base_parsed = urlparse(self.base_url)
        return (parsed.netloc == base_parsed.netloc and 
                parsed.path.startswith(base_parsed.path))
    
    def extract_content(self, url):
        try:
            print(f"  → Requesting URL: {url}")
            response = self.session.get(url, timeout=10)
            print(f"  → Status code: {response.status_code}")
            print(f"  → Content length: {len(response.text)}")
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Check if this is a JavaScript-rendered docs site
            if '<elements-api' in response.text:
                print(f"  → Detected Stoplight Elements (JavaScript-based docs)")
                return self.extract_from_openapi(url)
            
            # Remove navigation, footers, and other non-content elements
            for element in soup.find_all(['nav', 'footer', 'aside', 'script', 'style']):
                element.decompose()
            
            # Remove promotional content (if any)
            for element in soup.find_all(string=lambda text: text and "Stay organized with collections" in text):
                parent = element.parent
                while parent and parent.name != 'body':
                    if parent.get_text().strip().startswith("Stay organized with collections"):
                        parent.decompose()
                        break
                    parent = parent.parent
            
            # Find main content area
            content_area = (soup.find('main') or 
                          soup.find('article') or 
                          soup.find(class_=lambda x: x and 'content' in x.lower()) or
                          soup.find('body'))
            
            print(f"  → Content area found: {content_area.name if content_area else None}")
            
            if not content_area:
                return None, []
                
            # Extract text content
            title = soup.find('h1')
            title_text = title.get_text().strip() if title else url
            
            # Get all text content, preserving some structure
            text_content = []
            elements = content_area.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li', 'td', 'pre', 'code'])
            print(f"  → Found {len(elements)} content elements")
            
            for elem in elements:
                text = elem.get_text().strip()
                if text and len(text) > 10:  # Filter out very short text
                    if elem.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                        text_content.append(f"\n{'#' * int(elem.name[1])} {text}\n")
                    else:
                        text_content.append(text)
            
            print(f"  → Extracted {len(text_content)} text blocks")
            
            # Find links to other docs pages
            links = []
            for link in content_area.find_all('a', href=True):
                href = link['href']
                full_url = urljoin(url, href)
                if self.is_valid_docs_url(full_url) and full_url not in self.visited_urls:
                    links.append(full_url)
            
            return title_text, text_content, links
            
        except Exception as e:
            print(f"Error scraping {url}: {e}")
            return None, [], []
    
    def extract_from_openapi(self, base_url):
        """Extract content from OpenAPI JSON specification"""
        try:
            # Try to get the OpenAPI spec
            parsed_base = urlparse(base_url)
            openapi_url = f"{parsed_base.scheme}://{parsed_base.netloc}/api/v3/openapi.json"
            
            print(f"  → Fetching OpenAPI spec: {openapi_url}")
            response = self.session.get(openapi_url, timeout=10)
            response.raise_for_status()
            
            import json
            spec = json.loads(response.text)
            
            # Extract title and description
            title = spec.get('info', {}).get('title', 'API Documentation')
            description = spec.get('info', {}).get('description', '')
            
            content_blocks = []
            
            # Add main info
            if description:
                content_blocks.append(f"# {title}")
                content_blocks.append(description)
            
            # Extract paths/endpoints
            paths = spec.get('paths', {})
            for path, methods in paths.items():
                content_blocks.append(f"\n## {path}")
                
                for method, details in methods.items():
                    if isinstance(details, dict):
                        summary = details.get('summary', '')
                        description = details.get('description', '')
                        
                        content_blocks.append(f"\n### {method.upper()} {path}")
                        if summary:
                            content_blocks.append(summary)
                        if description:
                            content_blocks.append(description)
                            
                        # Add parameters
                        parameters = details.get('parameters', [])
                        if parameters:
                            content_blocks.append("\nParameters:")
                            for param in parameters:
                                param_name = param.get('name', '')
                                param_desc = param.get('description', '')
                                param_required = param.get('required', False)
                                required_text = ' (required)' if param_required else ''
                                content_blocks.append(f"- {param_name}{required_text}: {param_desc}")
            
            # Get links to other documentation pages if any
            changelog_url = f"{parsed_base.scheme}://{parsed_base.netloc}/docs/v3/changelog"
            
            print(f"  → Extracted {len(content_blocks)} content blocks from OpenAPI")
            return title, content_blocks, [changelog_url]
            
        except Exception as e:
            print(f"  → Error extracting from OpenAPI: {e}")
            return None, [], []
            
        except Exception as e:
            print(f"Error scraping {url}: {e}")
            return None, [], []
    
    def scrape_docs(self, max_pages=1000):
        queue = deque([self.base_url])
        page_count = 0
        
        while queue and page_count < max_pages:
            url = queue.popleft()
            
            if url in self.visited_urls:
                continue
                
            print(f"Scraping ({page_count + 1}/{max_pages}): {url}")
            self.visited_urls.add(url)
            
            result = self.extract_content(url)
            if len(result) == 3:
                title, content, links = result
            else:
                title, content = result
                links = []
            
            if content:
                self.scraped_content.append({
                    'url': url,
                    'title': title,
                    'content': content
                })
                print(f"  → Scraped content: {len(content)} blocks")
                
                # Add new links to queue
                for link in links:
                    if link not in self.visited_urls:
                        queue.append(link)
                        print(f"  → Added to queue: {link}")
            else:
                print(f"  → No content found on this page")
            
            page_count += 1
            time.sleep(1)  # Be respectful to the server
    
    def save_to_file(self):
        with open(self.output_file, 'w', encoding='utf-8') as f:
            f.write("Doc-Fetcher API Documentation\n")
            f.write("=" * 50 + "\n\n")
            
            for page in self.scraped_content:
                f.write(f"URL: {page['url']}\n")
                f.write(f"Title: {page['title']}\n")
                f.write("-" * 50 + "\n")
                
                for content_block in page['content']:
                    f.write(content_block + "\n")
                
                f.write("\n" + "=" * 50 + "\n\n")
        
        print(f"Documentation saved to {self.output_file}")
        print(f"Scraped {len(self.scraped_content)} pages")

def main():
    target_url = "https://ads-api.reddit.com/docs/v3/"
    
    # Read target URL from file if it exists
    try:
        with open('target.txt', 'r') as f:
            target_url = f.read().strip()
    except FileNotFoundError:
        pass
    
    scraper = DocScraper(target_url, "docs.txt")
    scraper.scrape_docs()
    scraper.save_to_file()

if __name__ == "__main__":
    main()