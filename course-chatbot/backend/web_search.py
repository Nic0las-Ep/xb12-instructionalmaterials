"""
Web Search Integration using SerpAPI
For finding textbook and platform information online
"""

import requests
import os
from typing import Dict, Optional, List

class WebSearch:
    def __init__(self):
        """
        Initialize SerpAPI client
        Requires SERPAPI_API_KEY environment variable
        """
        self.api_key = os.getenv('SERPAPI_API_KEY')
        self.base_url = 'https://serpapi.com/search'
        
        # Check if API key is valid (not empty or placeholder)
        if self.api_key and self.api_key not in ['your_serpapi_key_here', '', 'None', 'none']:
            print("✓ SerpAPI configured")
        else:
            self.api_key = None  # Set to None if invalid
            print("⚠ Warning: SERPAPI_API_KEY not found in environment variables")
    
    def search_textbook(self, course_name: str, course_level: str) -> Optional[Dict]:
        """
        Search for affordable textbook alternatives
        """
        if not self.api_key:
            return None
        
        try:
            query = f"affordable {course_name} textbook alternatives open educational resources"
            
            params = {
                'q': query,
                'api_key': self.api_key,
                'engine': 'google',
                'num': 5
            }
            
            response = requests.get(self.base_url, params=params, timeout=10)
            
            if response.status_code == 200:
                results = response.json()
                
                # Extract relevant information from search results
                if 'organic_results' in results and len(results['organic_results']) > 0:
                    # Focus on OER and affordable options
                    for result in results['organic_results']:
                        title = result.get('title', '')
                        link = result.get('link', '')
                        snippet = result.get('snippet', '')
                        
                        # Prioritize OpenStax, LibreTexts, and other OER sources
                        if any(keyword in link.lower() for keyword in ['openstax', 'libretexts', 'oer', 'opensource']):
                            return {
                                'title': title,
                                'cost': 0,  # OER resources are typically free
                                'url': link,
                                'source': 'web_search'
                            }
                    
                    # If no OER found, return first result with caveat
                    first_result = results['organic_results'][0]
                    return {
                        'title': first_result.get('title', 'Alternative Resource'),
                        'cost': 'See website',
                        'url': first_result.get('link', ''),
                        'source': 'web_search'
                    }
            
            return None
            
        except Exception as e:
            print(f"⚠ Error searching for textbooks: {str(e)}")
            return None
    
    def search_platform_reviews(self, platform_name: str, course_type: str) -> Dict:
        """
        Search for reviews and information about an assignment platform
        """
        if not self.api_key:
            return {
                'rating': 'Unknown',
                'reviews_found': False,
                'summary': 'Could not retrieve reviews'
            }
        
        try:
            query = f"{platform_name} reviews {course_type} courses rating"
            
            params = {
                'q': query,
                'api_key': self.api_key,
                'engine': 'google',
                'num': 3
            }
            
            response = requests.get(self.base_url, params=params, timeout=10)
            
            if response.status_code == 200:
                results = response.json()
                
                # Analyze results for sentiment
                if 'organic_results' in results and len(results['organic_results']) > 0:
                    snippets = [r.get('snippet', '') for r in results['organic_results']]
                    combined_text = ' '.join(snippets).lower()
                    
                    # Simple sentiment analysis
                    positive_words = ['good', 'great', 'excellent', 'helpful', 'effective', 'recommend']
                    negative_words = ['bad', 'poor', 'difficult', 'confusing', 'expensive', 'avoid']
                    
                    positive_count = sum(combined_text.count(word) for word in positive_words)
                    negative_count = sum(combined_text.count(word) for word in negative_words)
                    
                    if positive_count > negative_count:
                        sentiment = 'Positive'
                    elif negative_count > positive_count:
                        sentiment = 'Mixed'
                    else:
                        sentiment = 'Neutral'
                    
                    return {
                        'rating': sentiment,
                        'reviews_found': True,
                        'summary': snippets[0][:200] if snippets else 'Reviews available online'
                    }
            
            return {
                'rating': 'Unknown',
                'reviews_found': False,
                'summary': 'No reviews found'
            }
            
        except Exception as e:
            print(f"⚠ Error searching for reviews: {str(e)}")
            return {
                'rating': 'Unknown',
                'reviews_found': False,
                'summary': 'Error retrieving reviews'
            }
    
    def get_platform_url(self, platform_name: str) -> str:
        """
        Get the official URL for a platform based on its name
        Uses simple search to find official site
        """
        if not self.api_key:
            return f"https://www.google.com/search?q={platform_name.replace(' ', '+')}"
        
        try:
            query = f"{platform_name} official site"
            
            params = {
                'q': query,
                'api_key': self.api_key,
                'engine': 'google',
                'num': 1
            }
            
            response = requests.get(self.base_url, params=params, timeout=10)
            
            if response.status_code == 200:
                results = response.json()
                
                if 'organic_results' in results and len(results['organic_results']) > 0:
                    return results['organic_results'][0].get('link', '')
            
            return f"https://www.google.com/search?q={platform_name.replace(' ', '+')}"
            
        except Exception as e:
            print(f"⚠ Error getting platform URL: {str(e)}")
            return f"https://www.google.com/search?q={platform_name.replace(' ', '+')}"


# Standalone testing
if __name__ == '__main__':
    print("Testing Web Search Integration...")
    print("=" * 60)
    
    search = WebSearch()
    
    if search.api_key:
        # Test textbook search
        print("\nTesting Textbook Search...")
        textbook = search.search_textbook("Introduction to Biology", "introductory")
        
        if textbook:
            print(f"Title: {textbook['title']}")
            print(f"Cost: {textbook['cost']}")
            print(f"URL: {textbook['url']}")
        else:
            print("No textbook found")
        
        # Test platform reviews
        print("\nTesting Platform Review Search...")
        reviews = search.search_platform_reviews("Mastering Biology", "introductory biology")
        print(f"Rating: {reviews['rating']}")
        print(f"Reviews Found: {reviews['reviews_found']}")
        print(f"Summary: {reviews['summary']}")
        
        # Test platform URL lookup
        print("\nTesting Platform URL Lookup...")
        url = search.get_platform_url("Canvas LMS")
        print(f"URL: {url}")
    else:
        print("SerpAPI not configured - skipping tests")
    
    print("\n" + "=" * 60)
