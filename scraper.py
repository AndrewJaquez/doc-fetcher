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
        return (parsed.netloc == "developers.google.com" and 
                "/google-ads/api/docs/" in parsed.path)
    
    def extract_content(self, url):
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Remove navigation, footers, and other non-content elements
            for element in soup.find_all(['nav', 'footer', 'aside', 'script', 'style']):
                element.decompose()
            
            # Remove "Stay organized with collections" promotional content
            for element in soup.find_all(text=lambda text: text and "Stay organized with collections" in text):
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
            
            if not content_area:
                return None, []
                
            # Extract text content
            title = soup.find('h1')
            title_text = title.get_text().strip() if title else url
            
            # Get all text content, preserving some structure
            text_content = []
            for elem in content_area.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li', 'td', 'pre', 'code']):
                text = elem.get_text().strip()
                if text and len(text) > 10:  # Filter out very short text
                    if elem.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                        text_content.append(f"\n{'#' * int(elem.name[1])} {text}\n")
                    else:
                        text_content.append(text)
            
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
    
    def scrape_docs(self, max_pages=50):
        queue = deque([self.base_url])
        page_count = 0
        
        while queue and page_count < max_pages:
            url = queue.popleft()
            
            if url in self.visited_urls:
                continue
                
            print(f"Scraping ({page_count + 1}/{max_pages}): {url}")
            self.visited_urls.add(url)
            
            title, content, links = self.extract_content(url)
            
            if content:
                self.scraped_content.append({
                    'url': url,
                    'title': title,
                    'content': content
                })
                
                # Add new links to queue
                for link in links:
                    if link not in self.visited_urls:
                        queue.append(link)
            
            page_count += 1
            time.sleep(1)  # Be respectful to the server
    
    def save_to_file(self):
        with open(self.output_file, 'w', encoding='utf-8') as f:
            f.write("Google Ads API Documentation\n")
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
    target_url = "https://developers.google.com/google-ads/api/docs/start"
    
    # Read target URL from file if it exists
    try:
        with open('target.txt', 'r') as f:
            target_url = f.read().strip()
    except FileNotFoundError:
        pass
    
    scraper = DocScraper(target_url, "google_ads_docs.txt")
    scraper.scrape_docs()
    scraper.save_to_file()

if __name__ == "__main__":
    main()