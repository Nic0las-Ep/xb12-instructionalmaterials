# Course Materials Chatbot
### AI-Powered Textbook and Assignment Platform Suggestions for Professors
**Foothill-De Anza Community College District**

---

## 📋 Overview

This chatbot helps professors find affordable textbook and assignment platform alternatives based on historical data from previous instructors. It features:

- **Deterministic suggestions** from real professor data
- **AI-powered recommendations** via AWS Bedrock (Claude Sonnet)
- **Web search integration** for additional options
- **Proactive assistance** - auto-suggests when course names are detected
- **Cost-focused** - prioritizes free and low-cost alternatives

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (HTML/CSS/JS)                │
│                  Standalone Chatbot Widget               │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP/JSON
                       ▼
┌─────────────────────────────────────────────────────────┐
│                  Flask Backend (Python)                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │     CSV      │  │     AWS      │  │   SerpAPI    │  │
│  │   Database   │  │   Bedrock    │  │  Web Search  │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## 📁 Project Structure

```
course-chatbot/
├── backend/
│   ├── app.py                 # Flask API server
│   ├── suggestions.py         # Suggestion engine & CSV parsing
│   ├── aws_bedrock.py         # AWS Bedrock (Claude) integration
│   ├── web_search.py          # SerpAPI web search
│   ├── requirements.txt       # Python dependencies
│   └── .env.example           # Environment variables template
├── frontend/
│   ├── chatbot-widget.html    # Standalone chatbot widget
│   ├── chatbot.js             # Frontend logic
│   └── demo.html              # Demo integration page
├── data/
│   └── previous_courses.csv   # Historical course data
├── .gitignore
└── README.md
```

---

## 🚀 Quick Start

### 1. Prerequisites

- **Python 3.8+**
- **pip** (Python package manager)
- **AWS Account** with Bedrock access (optional but recommended)
- **SerpAPI Key** (optional, for web search)

### 2. Backend Setup

```bash
# Navigate to backend directory
cd course-chatbot/backend

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env with your credentials (see Configuration section)

# Run the Flask server
python app.py
```

The backend will start at `http://localhost:5000`

### 3. Frontend Setup

```bash
# Navigate to frontend directory
cd course-chatbot/frontend

# Open demo page in browser
open demo.html
# Or on Linux:
# xdg-open demo.html
```

Alternatively, serve with a simple HTTP server:

```bash
python3 -m http.server 8000
# Visit http://localhost:8000/demo.html
```

---

## ⚙️ Configuration

### AWS Bedrock Setup

1. **Create AWS Account** (if you don't have one)
2. **Enable AWS Bedrock** in your region (us-east-1 recommended)
3. **Request access to Claude models** in the Bedrock console
4. **Create IAM user** with Bedrock permissions:
   - `bedrock:InvokeModel`
   - `bedrock:InvokeModelWithResponseStream`
5. **Generate access keys** and add to `.env`:

```bash
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

### SerpAPI Setup

1. **Sign up** at [https://serpapi.com/](https://serpapi.com/)
2. **Get API key** from dashboard (free tier: 100 searches/month)
3. **Add to `.env`**:

```bash
SERPAPI_API_KEY=your_serpapi_key_here
```

### Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `AWS_REGION` | Optional | AWS region for Bedrock (default: us-east-1) |
| `AWS_ACCESS_KEY_ID` | Optional | AWS access key for Bedrock |
| `AWS_SECRET_ACCESS_KEY` | Optional | AWS secret key for Bedrock |
| `SERPAPI_API_KEY` | Optional | SerpAPI key for web search |

**Note:** The system works without AWS/SerpAPI but will only show CSV-based suggestions.

---

## 📊 Data Management

### CSV Data Format

The `previous_courses.csv` file contains historical course data:

```csv
professor_name,class_name,course_number,crn_code,section,textbook_title,textbook_cost,textbook_url,platform_name,platform_cost,platform_url
Dr. Sarah Chen,Introduction to Biology,BIOL 10,12783,01Y,Campbell Biology,145,https://...,Mastering Biology,120,https://...
```

### Adding New Courses

1. Open `data/previous_courses.csv`
2. Add a new row with course information
3. Restart the Flask backend
4. The new data will be immediately available

### Updating Existing Data

- Edit the CSV file directly
- Ensure all required fields are present
- Costs should be numeric (0 for free)
- URLs should be complete (include https://)

---

## 🔌 API Endpoints

### POST `/api/suggestions`

Get suggestions for a course.

**Request:**
```json
{
  "query": "Biology 10"
}
```

**Response:**
```json
{
  "type": "suggestions",
  "data": {
    "courseName": "BIOL 10",
    "textbooks": [
      {
        "title": "Biology by OpenStax",
        "cost": 0,
        "url": "https://openstax.org/..."
      }
    ],
    "platforms": [
      {
        "name": "Top Hat",
        "cost": 65,
        "url": "https://tophat.com"
      }
    ],
    "aiSuggestion": {
      "title": "LibreTexts Biology",
      "cost": 0,
      "url": "https://bio.libretexts.org"
    }
  }
}
```

### GET `/api/health`

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "message": "Course Material Chatbot API is running"
}
```

### GET `/api/courses`

List all available courses (for debugging).

**Response:**
```json
{
  "count": 5,
  "courses": [
    {
      "course_number": "BIOL 10",
      "class_name": "Introduction to Biology",
      "textbook_count": 2,
      "platform_count": 2
    }
  ]
}
```

---

## 🎨 Embedding the Chatbot

### Option 1: Simple Embed (Recommended)

Copy the chatbot HTML directly into your application:

```html
<!-- Include chatbot styles and structure -->
<link rel="stylesheet" href="path/to/chatbot-widget.css">

<!-- Chatbot container at bottom-right -->
<div id="chatbot-container">
  <!-- ... chatbot HTML ... -->
</div>

<!-- Include chatbot script -->
<script src="path/to/chatbot.js"></script>
```

### Option 2: iframe Embed

```html
<iframe 
  src="http://localhost:8000/chatbot-widget.html" 
  style="position:fixed;bottom:20px;right:20px;width:400px;height:600px;border:none;z-index:9999;">
</iframe>
```

### Option 3: Direct Integration

Copy the code from `chatbot-widget.html` and `chatbot.js` directly into your existing pages.

**Update the API URL:**
```javascript
// In chatbot.js, line 2:
const API_BASE_URL = 'http://your-backend-server.com/api';
```

---

## 🧪 Testing

### Test Backend

```bash
cd course-chatbot/backend

# Test suggestion engine
python suggestions.py

# Test AWS Bedrock integration
python aws_bedrock.py

# Test web search
python web_search.py

# Start Flask server and test endpoints
python app.py

# In another terminal:
curl http://localhost:5000/api/health
curl -X POST http://localhost:5000/api/suggestions \
  -H "Content-Type: application/json" \
  -d '{"query": "Biology 10"}'
```

### Test Frontend

1. Open `demo.html` in a browser
2. Click the chatbot button (bottom-right)
3. Type "Biology 10" or "BIOL 10"
4. Verify suggestions appear
5. Check browser console for errors (F12)

---

## 🎯 Usage Examples

### For Professors

**Example 1: Simple course query**
```
User: "Biology 10"
Bot: Shows textbooks and platforms with costs, sorted by price
```

**Example 2: Full course name**
```
User: "Introduction to Programming"
Bot: Identifies CS 1A and shows relevant materials
```

**Example 3: General question**
```
User: "What platforms are available?"
Bot: Provides general guidance or asks for course name
```

### Auto-Suggestion Trigger

The chatbot automatically pops up suggestions when professors type course-related keywords:
- "Biology", "Math", "Chemistry", "English", "CS"
- Triggers after typing 3+ characters

---

## 🛠️ Customization

### Styling

Edit the CSS in `chatbot-widget.html` or `demo.html`:

```css
/* Change chatbot colors */
#chatbot-button {
  background: linear-gradient(135deg, #your-color, #your-darker-color);
}

/* Change header colors */
#chatbot-header {
  background: linear-gradient(135deg, #your-color, #your-darker-color);
}
```

### Behavior

Edit `chatbot.js`:

```javascript
// Change auto-suggestion trigger length (line 38)
if (!chatState.hasShownAutoSuggestion && value.length > 5) {
  // Now triggers after 5 characters instead of 3
}

// Change course keywords (line 40)
const courseKeywords = ['biol', 'math', 'chem', 'your-keyword'];
```

### AI Prompts

Edit `aws_bedrock.py`:

```python
# Modify the prompt in get_textbook_suggestion() method
prompt = f"""Your custom prompt here...
Course: {course_info['display_name']}
..."""
```

---

## 🔒 Security Notes

1. **Never commit `.env` file** to version control
2. **Use environment variables** for all credentials
3. **Enable CORS carefully** - restrict origins in production:
   ```python
   # In app.py
   CORS(app, origins=['https://your-production-domain.com'])
   ```
4. **Rate limit API** in production to prevent abuse
5. **Sanitize user input** before logging or displaying

---

## 🐛 Troubleshooting

### Backend Issues

**Problem:** Flask won't start
```bash
# Check if port 5000 is in use
lsof -i :5000
# Kill the process or use a different port
python app.py --port 5001
```

**Problem:** AWS Bedrock errors
- Verify AWS credentials are correct
- Check IAM permissions include `bedrock:InvokeModel`
- Ensure Claude model access is enabled in Bedrock console
- Verify region is correct (us-east-1 or us-west-2)

**Problem:** CSV file not found
```bash
# Check file path
ls -la data/previous_courses.csv
# Verify CSV encoding is UTF-8
file data/previous_courses.csv
```

### Frontend Issues

**Problem:** Chatbot not appearing
- Check browser console (F12) for JavaScript errors
- Verify backend is running at `http://localhost:5000`
- Check CORS headers in network tab

**Problem:** API requests failing
- Verify backend URL in `chatbot.js` (line 2)
- Check if backend is accessible: `curl http://localhost:5000/api/health`
- Look for CORS errors in browser console

**Problem:** Auto-suggestions not working
- Type more than 3 characters
- Include course keywords: "biol", "math", "chem", etc.
- Check browser console for errors

---

## 📈 Future Enhancements

Potential improvements for future versions:

- [ ] User authentication for professors
- [ ] Admin dashboard for managing CSV data
- [ ] Integration with college course catalog API
- [ ] Student reviews and ratings for resources
- [ ] Cost comparison charts
- [ ] Email notifications for new affordable options
- [ ] Multi-language support
- [ ] Mobile app version
- [ ] Integration with LMS (Canvas, Blackboard)
- [ ] Analytics dashboard for resource usage

---

## 👥 For Your Development Team

### Integration with Existing Python Form App

Your teammate's Python form application can integrate this chatbot:

**Method 1: Embed the widget**
```python
# In your Flask/Django template
{{ chatbot_widget|safe }}
```

**Method 2: Use the API directly**
```python
import requests

def get_course_suggestions(course_name):
    response = requests.post(
        'http://localhost:5000/api/suggestions',
        json={'query': course_name}
    )
    return response.json()
```

**Method 3: Import suggestion engine**
```python
# In your Python app
from course_chatbot.backend.suggestions import SuggestionEngine

engine = SuggestionEngine()
suggestions = engine.get_csv_suggestions(course_info)
```

---

## 📄 License

This project is created for Foothill-De Anza Community College District.

---

## 🆘 Support

For questions or issues:

1. Check this README first
2. Review the Troubleshooting section
3. Check backend logs: `python app.py` output
4. Check browser console (F12) for frontend errors
5. Test API endpoints with curl/Postman

---

## 🎓 Credits

Built for Foothill-De Anza Community College District to help professors find affordable course materials and reduce student costs.

**Technologies Used:**
- Frontend: HTML, CSS, JavaScript (Vanilla)
- Backend: Python, Flask
- AI: AWS Bedrock (Claude 3.5 Sonnet)
- Search: SerpAPI
- Data: CSV files (easily upgradeable to PostgreSQL/MySQL)

---

**Last Updated:** July 2026
**Version:** 1.0.0
