from flask import Flask, jsonify, render_template, request
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import re
import time

app = Flask(__name__)

# Cache configurations
CACHE_DURATION = 600  # 10 minutes cache
cached_data = None
last_fetch_time = 0

FEED_URL = "https://docs.cloud.google.com/feeds/bigquery-release-notes.xml"

def clean_html_to_plain_text(html_content):
    """
    Extracts text from HTML structure and cleans up whitespaces,
    leaving a readable plain text string suitable for tweet drafts.
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        # Replace anchors with text only to keep the tweet readable
        for a in soup.find_all('a'):
            a.replace_with(a.get_text())
            
        text = soup.get_text(separator=" ").strip()
        # Clean double spaces and line-break spaces
        text = re.sub(r'\s+', ' ', text)
        return text
    except Exception as e:
        print(f"Error cleaning HTML: {e}")
        return html_content

def fetch_and_parse_feed():
    """
    Downloads the BigQuery XML Atom feed, processes entries,
    and parses inner HTML updates dynamically.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    response = requests.get(FEED_URL, headers=headers, timeout=15)
    response.raise_for_status()
    
    # Process XML tree
    xml_data = response.content
    root = ET.fromstring(xml_data)
    
    # Atom namespaces
    namespaces = {'atom': 'http://www.w3.org/2005/Atom'}
    
    feed_title_el = root.find('atom:title', namespaces)
    feed_title = feed_title_el.text if feed_title_el is not None else "BigQuery Release Notes"
    
    feed_updated_el = root.find('atom:updated', namespaces)
    feed_updated = feed_updated_el.text if feed_updated_el is not None else ""
    
    updates = []
    
    # Process each day entry
    for entry in root.findall('atom:entry', namespaces):
        title_el = entry.find('atom:title', namespaces)
        updated_el = entry.find('atom:updated', namespaces)
        id_el = entry.find('atom:id', namespaces)
        
        # Link resolution
        link_el = entry.find('atom:link[@rel="alternate"]', namespaces)
        if link_el is None:
            link_el = entry.find('atom:link', namespaces)
            
        date_str = title_el.text if title_el is not None else "Unknown Date"
        updated_val = updated_el.text if updated_el is not None else ""
        link_url = link_el.attrib.get('href', '') if link_el is not None else ""
        entry_id = id_el.text if id_el is not None else ""
        
        content_el = entry.find('atom:content', namespaces)
        if content_el is not None and content_el.text:
            content_html = content_el.text
            
            # Use BeautifulSoup to split updates grouped by <h3> type headers
            soup = BeautifulSoup(content_html, 'html.parser')
            
            current_type = None
            current_elements = []
            updates_in_entry = []
            
            for element in soup.contents:
                # If we encounter an h3 tag, we start a new category block
                if element.name == 'h3':
                    if current_elements:
                        html_body = "".join(str(e) for e in current_elements).strip()
                        if html_body:
                            updates_in_entry.append((current_type or "Update", html_body))
                        current_elements = []
                    current_type = element.get_text().strip()
                elif element.name is not None:
                    current_elements.append(element)
                else:
                    if element.strip():
                        current_elements.append(element)
            
            # Capture the last remaining block of elements
            if current_elements:
                html_body = "".join(str(e) for e in current_elements).strip()
                if html_body:
                    updates_in_entry.append((current_type or "Update", html_body))
            
            # Fallback if no <h3> tags existed but HTML was present
            if not updates_in_entry and content_html.strip():
                updates_in_entry.append(("Update", content_html.strip()))
                
            # Populate structured JSON objects for each sub-update
            for idx, (h3_type, html_body) in enumerate(updates_in_entry):
                sub_id = f"{entry_id}_{idx}"
                plain_text = clean_html_to_plain_text(html_body)
                
                updates.append({
                    "id": sub_id,
                    "date": date_str,
                    "updated": updated_val,
                    "type": h3_type,
                    "html": html_body,
                    "plain_text": plain_text,
                    "url": link_url
                })
                
    return {
        "feed_title": feed_title,
        "feed_updated": feed_updated,
        "updates": updates
    }

def get_data(force=False):
    global cached_data, last_fetch_time
    now = time.time()
    
    if force or cached_data is None or (now - last_fetch_time > CACHE_DURATION):
        cached_data = fetch_and_parse_feed()
        last_fetch_time = now
        
    return cached_data

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/releases')
def releases():
    force_refresh = request.args.get('refresh', 'false').lower() == 'true'
    try:
        data = get_data(force=force_refresh)
        return jsonify({
            "status": "success",
            "data": data,
            "cached": not force_refresh
        })
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        return jsonify({
            "status": "error",
            "message": str(e),
            "details": error_details
        }), 500

if __name__ == '__main__':
    # Running locally on port 5050
    app.run(host='0.0.0.0', port=5050, debug=True)
