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
            
            # Separate regular links from navigation links
            regular_links = []
            next_links = []
            
            # Find regular links to other docs pages
            for link in content_area.find_all('a', href=True):
                href = link['href']
                full_url = urljoin(url, href)
                if self.is_valid_docs_url(full_url) and full_url not in self.visited_urls:
                    regular_links.append(full_url)
            
            # Also look for Next buttons and pagination links in the entire page
            next_buttons = soup.find_all('a', href=True, string=lambda text: text and 'next' in text.lower())
            for button in next_buttons:
                href = button['href']
                full_url = urljoin(url, href)
                if self.is_valid_docs_url(full_url) and full_url not in self.visited_urls and full_url not in regular_links:
                    next_links.append(full_url)
                    print(f"  → Found Next button: {full_url}")
            
            # Look for navigation arrows and buttons with specific classes/attributes
            nav_selectors = [
                'a[aria-label*="next"]',
                'a[aria-label*="Next"]',
                'a[class*="next"]',
                'a[class*="pagination"]',
                '.next a',
                '.pagination a',
                '[class*="nav"] a',
                # Footer navigation patterns
                'nav[class*="footer"] a',
                '.md-footer a',
                'footer nav a',
                'footer a',
                # Material Design footer patterns
                '.md-footer__link--next',
                'a.md-footer__link--next',
                # Generic footer navigation
                '[class*="footer"] a[class*="next"]',
                '[class*="footer"] a[aria-label*="next"]',
                '[class*="footer"] a[aria-label*="Next"]',
                # Documentation navigation patterns
                '.doc-nav a',
                '.docs-nav a',
                '.page-nav a',
                '[class*="page-navigation"] a',
                '[class*="doc-navigation"] a'
            ]
            
            for selector in nav_selectors:
                try:
                    nav_links = soup.select(selector)
                    for nav_link in nav_links:
                        if nav_link.get('href'):
                            href = nav_link['href']
                            full_url = urljoin(url, href)
                            if self.is_valid_docs_url(full_url) and full_url not in self.visited_urls and full_url not in regular_links and full_url not in next_links:
                                # Check if this looks like a next/forward navigation
                                link_text = nav_link.get_text().strip().lower()
                                link_classes = str(nav_link.get('class', [])).lower()
                                aria_label = nav_link.get('aria-label', '').lower()
                                
                                # Keywords for next/forward navigation
                                next_keywords = ['next', '→', '>', 'continue', 'forward', 'siguiente']
                                
                                # Check text content, classes, and aria-label
                                is_next_link = (
                                    any(keyword in link_text for keyword in next_keywords) or
                                    any(keyword in link_classes for keyword in ['next', 'forward']) or
                                    any(keyword in aria_label for keyword in next_keywords) or
                                    'next' in aria_label
                                )
                                
                                # Special handling for Material Design and common patterns
                                if ('md-footer__link--next' in link_classes or 
                                    'footer' in link_classes or
                                    nav_link.find(string=lambda text: text and 'next' in text.lower())):
                                    is_next_link = True
                                
                                if is_next_link:
                                    next_links.append(full_url)
                                    print(f"  → Found navigation link: {full_url} (text: '{nav_link.get_text().strip()}')")
                except Exception as e:
                    # Continue if CSS selector fails
                    continue
            
            # Return next links first for sequential navigation, then regular links
            all_links = next_links + regular_links
            
            return title_text, text_content, all_links
            
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
        # Use two queues: priority queue for next/navigation links, regular queue for other links
        priority_queue = deque([self.base_url])
        regular_queue = deque()
        page_count = 0
        
        while (priority_queue or regular_queue) and page_count < max_pages:
            # Always prioritize navigation links over regular links
            if priority_queue:
                url = priority_queue.popleft()
                queue_type = "PRIORITY"
            else:
                url = regular_queue.popleft()
                queue_type = "REGULAR"
            
            if url in self.visited_urls:
                continue
                
            print(f"Scraping ({page_count + 1}/{max_pages}) [{queue_type}]: {url}")
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
                
                # Add new links to appropriate queues
                # First few links are next/navigation links (returned first from extract_content)
                next_link_count = 0
                for i, link in enumerate(links):
                    if link not in self.visited_urls:
                        # First 2-3 links are likely next/navigation links based on our prioritization
                        if i < 3 and any(indicator in link.lower() for indicator in ['next', 'plan', 'step', 'part']):
                            priority_queue.append(link)
                            print(f"  → Added to priority queue: {link}")
                            next_link_count += 1
                        else:
                            regular_queue.append(link)
                            print(f"  → Added to regular queue: {link}")
                
                if next_link_count > 0:
                    print(f"  → Found {next_link_count} navigation links to prioritize")
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