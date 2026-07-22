"""
Suggestion Engine for Course Materials
Handles CSV data querying and AI-powered suggestions
"""

import csv
import os
import re
from typing import Dict, List, Optional

# Import AI and web search modules
try:
    from aws_bedrock import BedrockAI
    BEDROCK_AVAILABLE = True
except ImportError:
    BEDROCK_AVAILABLE = False
    print("⚠ AWS Bedrock module not available")

try:
    from web_search import WebSearch
    WEBSEARCH_AVAILABLE = True
except ImportError:
    WEBSEARCH_AVAILABLE = False
    print("⚠ Web Search module not available")

class SuggestionEngine:
    def __init__(self):
        self.csv_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'previous_courses.csv')
        self.course_data = self._load_csv_data()
        
        # Initialize AI and web search
        self.ai = BedrockAI() if BEDROCK_AVAILABLE else None
        self.web_search = WebSearch() if WEBSEARCH_AVAILABLE else None
        
        # Course name mappings and aliases
        self.course_aliases = {
            'bio': 'BIOL',
            'biology': 'BIOL',
            'calc': 'MATH',
            'calculus': 'MATH',
            'math': 'MATH',
            'mathematics': 'MATH',
            'cs': 'CS',
            'comp sci': 'CS',
            'computer science': 'CS',
            'programming': 'CS',
            'english': 'ENGL',
            'composition': 'ENGL',
            'chem': 'CHEM',
            'chemistry': 'CHEM'
        }
    
    def _load_csv_data(self) -> List[Dict]:
        """Load course data from CSV file"""
        data = []
        try:
            with open(self.csv_path, 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    data.append(row)
            print(f"✓ Loaded {len(data)} course records from CSV")
        except FileNotFoundError:
            print(f"⚠ Warning: CSV file not found at {self.csv_path}")
        except Exception as e:
            print(f"⚠ Error loading CSV: {str(e)}")
        
        return data
    
    def parse_course_query(self, query: str) -> Optional[Dict]:
        """
        Parse user query to extract course information
        Examples: "Biology 10", "BIOL 10", "Introduction to Biology", "CS 1A"
        """
        query_lower = query.lower().strip()

        # Pattern 1: Department name + number (e.g., "Biology 10", "Calculus 1A")
        # Checked before the direct-code pattern below, otherwise a full
        # department word like "Biology" gets treated as a literal (and
        # non-matching) department code instead of being mapped to "BIOL".
        pattern1 = r'(biology|bio|calculus|calc|chemistry|chem|english|programming|computer science|cs|math|mathematics)\s*(\d+[A-Za-z]*)'
        match1 = re.search(pattern1, query_lower)
        if match1:
            dept_word = match1.group(1)
            number = match1.group(2).upper()

            # Map to department code
            dept_code = self.course_aliases.get(dept_word, dept_word.upper())

            return {
                'department': dept_code,
                'number': number,
                'display_name': f"{dept_code} {number}",
                'original_query': query
            }

        # Pattern 2: Direct course code (e.g., "BIOL 10", "CS 1A")
        pattern2 = r'([A-Z]+)\s*(\d+[A-Z]*)'
        match2 = re.search(pattern2, query.upper())
        if match2:
            dept = match2.group(1)
            number = match2.group(2)
            return {
                'department': dept,
                'number': number,
                'display_name': f"{dept} {number}",
                'original_query': query
            }
        
        # Pattern 3: Full course name search (e.g., "Introduction to Biology")
        for dept_word, dept_code in self.course_aliases.items():
            if dept_word in query_lower:
                # Search in CSV for matching course names
                for row in self.course_data:
                    if query_lower in row['class_name'].lower():
                        course_num = row['course_number'].split()[-1]  # Extract number part
                        return {
                            'department': dept_code,
                            'number': course_num,
                            'display_name': row['class_name'],
                            'original_query': query
                        }
        
        return None
    
    def get_csv_suggestions(self, course_info: Dict) -> Dict:
        """
        Get suggestions from CSV data based on course information
        Returns textbooks and platforms sorted by cost (ascending)
        """
        textbooks = []
        platforms = []
        
        # Search for matching courses in CSV
        for row in self.course_data:
            course_num = row['course_number']
            course_parts = course_num.split()

            # Check if this row matches the requested course (exact
            # department/number match, not substring, so e.g. "MATH 1"
            # doesn't incorrectly match "MATH 1A")
            if (len(course_parts) >= 2
                    and course_parts[0] == course_info['department']
                    and course_parts[1] == course_info['number']):
                # Extract textbook info
                if row['textbook_title']:
                    textbook = {
                        'title': row['textbook_title'],
                        'cost': float(row['textbook_cost']) if row['textbook_cost'] else 0,
                        'url': row['textbook_url']
                    }
                    # Avoid duplicates
                    if not any(t['title'] == textbook['title'] for t in textbooks):
                        textbooks.append(textbook)
                
                # Extract platform info
                if row['platform_name']:
                    platform = {
                        'name': row['platform_name'],
                        'cost': float(row['platform_cost']) if row['platform_cost'] else 0,
                        'url': row['platform_url']
                    }
                    # Avoid duplicates
                    if not any(p['name'] == platform['name'] for p in platforms):
                        platforms.append(platform)
        
        # Sort by cost (ascending - cheapest first)
        textbooks.sort(key=lambda x: x['cost'])
        platforms.sort(key=lambda x: x['cost'])
        
        return {
            'textbooks': textbooks,
            'platforms': platforms
        }
    
    def get_ai_suggestion(self, course_info: Dict) -> Optional[Dict]:
        """
        Get AI-powered additional suggestion using AWS Bedrock (Claude)
        Falls back to web search if Bedrock is not available
        Returns one additional affordable textbook/resource suggestion
        """
        suggestion = None
        
        # Try AWS Bedrock first (preferred method)
        if self.ai:
            try:
                suggestion = self.ai.get_textbook_suggestion(course_info)
                if suggestion:
                    print(f"✓ Got AI suggestion from Bedrock: {suggestion['title']}")
                    return suggestion
            except Exception as e:
                print(f"⚠ Bedrock suggestion failed: {str(e)}")
        
        # Fallback to web search
        if self.web_search and not suggestion:
            try:
                suggestion = self.web_search.search_textbook(
                    course_info['display_name'],
                    'introductory'
                )
                if suggestion:
                    print(f"✓ Got suggestion from web search: {suggestion['title']}")
                    return suggestion
            except Exception as e:
                print(f"⚠ Web search suggestion failed: {str(e)}")
        
        # No AI suggestion available
        return None
    
    def validate_platform_with_reviews(self, platform_name: str, course_info: Dict) -> Dict:
        """
        Validate platform using AI and web search reviews
        """
        validation = {'is_good': True, 'reason': 'Used by other professors'}
        
        # Try AI validation first
        if self.ai:
            try:
                ai_validation = self.ai.validate_platform(
                    platform_name,
                    course_info.get('display_name', 'introductory')
                )
                if ai_validation:
                    validation = {
                        'is_good': ai_validation.get('is_valid', True),
                        'reason': ai_validation.get('reason', 'No specific reason')
                    }
            except Exception as e:
                print(f"⚠ Platform validation error: {str(e)}")
        
        # Supplement with web search reviews
        if self.web_search:
            try:
                reviews = self.web_search.search_platform_reviews(
                    platform_name,
                    course_info.get('display_name', '')
                )
                if reviews.get('reviews_found'):
                    validation['reviews'] = reviews
            except Exception as e:
                print(f"⚠ Review search error: {str(e)}")
        
        return validation
    
    def get_all_courses(self) -> List[Dict]:
        """
        Get all available courses (for debugging and API access)
        """
        unique_courses = {}
        
        for row in self.course_data:
            course_key = row['course_number']
            if course_key not in unique_courses:
                unique_courses[course_key] = {
                    'course_number': row['course_number'],
                    'class_name': row['class_name'],
                    'textbook_count': 0,
                    'platform_count': 0
                }
            
            if row['textbook_title']:
                unique_courses[course_key]['textbook_count'] += 1
            if row['platform_name']:
                unique_courses[course_key]['platform_count'] += 1
        
        return list(unique_courses.values())


# Standalone testing
if __name__ == '__main__':
    print("Testing Suggestion Engine...")
    print("=" * 60)
    
    engine = SuggestionEngine()
    
    # Test queries
    test_queries = [
        "Biology 10",
        "BIOL 10",
        "Introduction to Biology",
        "CS 1A",
        "Calculus",
        "MATH 1A",
        "Chemistry 1A"
    ]
    
    for query in test_queries:
        print(f"\nQuery: '{query}'")
        course_info = engine.parse_course_query(query)
        
        if course_info:
            print(f"  Parsed: {course_info['display_name']}")
            suggestions = engine.get_csv_suggestions(course_info)
            print(f"  Textbooks: {len(suggestions['textbooks'])}")
            print(f"  Platforms: {len(suggestions['platforms'])}")
            
            if suggestions['textbooks']:
                print("  Top textbook:", suggestions['textbooks'][0]['title'])
        else:
            print("  ✗ Could not parse query")
    
    print("\n" + "=" * 60)
