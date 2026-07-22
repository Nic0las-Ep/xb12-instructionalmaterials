"""
Flask Backend for Course Material Chatbot
Foothill-De Anza Community College District
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import csv
import os

load_dotenv()

from suggestions import SuggestionEngine

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend communication

# Initialize suggestion engine
suggestion_engine = SuggestionEngine()

@app.route('/api/suggestions', methods=['POST'])
def get_suggestions():
    """
    Main endpoint for getting course material suggestions
    """
    try:
        data = request.get_json()
        query = data.get('query', '').strip()
        
        if not query:
            return jsonify({
                'type': 'message',
                'message': 'Please enter a course name to get suggestions.'
            })
        
        # Extract course information from query
        course_info = suggestion_engine.parse_course_query(query)
        
        if not course_info:
            return jsonify({
                'type': 'message',
                'message': 'I couldn\'t identify a course from your query. Please try entering something like "Biology 10" or "Introduction to Biology".'
            })
        
        # Get suggestions from CSV data
        csv_suggestions = suggestion_engine.get_csv_suggestions(course_info)
        
        if not csv_suggestions['textbooks'] and not csv_suggestions['platforms']:
            return jsonify({
                'type': 'message',
                'message': f'I don\'t have any data for {course_info["display_name"]} yet. Would you like me to search for alternatives online?'
            })
        
        # Get AI-powered additional suggestion (if enabled)
        ai_suggestion = suggestion_engine.get_ai_suggestion(course_info)
        
        # Format response
        response_data = {
            'courseName': course_info['display_name'],
            'textbooks': csv_suggestions['textbooks'],
            'platforms': csv_suggestions['platforms'],
            'aiSuggestion': ai_suggestion
        }
        
        return jsonify({
            'type': 'suggestions',
            'data': response_data
        })
        
    except Exception as e:
        print(f"Error in /api/suggestions: {str(e)}")
        return jsonify({
            'type': 'error',
            'message': 'An error occurred while processing your request.'
        }), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """
    Health check endpoint
    """
    return jsonify({
        'status': 'healthy',
        'message': 'Course Material Chatbot API is running'
    })

@app.route('/api/courses', methods=['GET'])
def get_all_courses():
    """
    Endpoint to get all available courses (for debugging)
    """
    try:
        courses = suggestion_engine.get_all_courses()
        return jsonify({
            'count': len(courses),
            'courses': courses
        })
    except Exception as e:
        print(f"Error in /api/courses: {str(e)}")
        return jsonify({
            'error': 'Failed to retrieve courses'
        }), 500

@app.route('/api/courses', methods=['POST'])
def add_course():
    """
    Save a professor's submitted course form as a new record in the
    historical dataset, so future suggestions include it.
    """
    try:
        data = request.get_json()

        required_fields = ['professor_name', 'class_name', 'course_number', 'crn_code', 'section']
        missing = [field for field in required_fields if not data.get(field, '').strip()]
        if missing:
            return jsonify({
                'error': f"Missing required fields: {', '.join(missing)}"
            }), 400

        record = {field: data.get(field, '').strip() for field in [
            'professor_name', 'class_name', 'course_number', 'crn_code', 'section',
            'textbook_title', 'textbook_cost', 'textbook_url',
            'platform_name', 'platform_cost', 'platform_url'
        ]}

        suggestion_engine.add_course_record(record)

        return jsonify({
            'success': True,
            'message': 'Course information saved.'
        })

    except Exception as e:
        print(f"Error in /api/courses POST: {str(e)}")
        return jsonify({
            'error': 'Failed to save course information.'
        }), 500

if __name__ == '__main__':
    print("=" * 60)
    print("Course Material Chatbot Backend")
    print("Foothill-De Anza Community College District")
    print("=" * 60)
    print("Starting Flask server on http://localhost:5001")
    print("API Endpoints:")
    print("  - POST /api/suggestions - Get course suggestions")
    print("  - GET  /api/health      - Health check")
    print("  - GET  /api/courses     - List all courses")
    print("  - POST /api/courses     - Save a submitted course record")
    print("=" * 60)
    
    app.run(debug=True, host='0.0.0.0', port=5001)
