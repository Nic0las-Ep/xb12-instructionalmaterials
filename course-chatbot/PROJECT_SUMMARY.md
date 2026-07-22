# Project Summary: Course Materials Chatbot
**Foothill-De Anza Community College District**

---

## 📋 **Project Overview**

We are building an **AI-powered chatbot** that helps professors find affordable textbook and assignment platform alternatives. The chatbot appears as a floating button in the bottom-right corner of a course information form, offering suggestions based on:

1. **Historical data** from previous professors (CSV file)
2. **Web search** (SerpAPI - optional)
3. **AI suggestions** (AWS Bedrock/Claude - optional, currently not implemented)

---

## 🎯 **Project Goals**

- Help **new professors** reduce starting stress
- Suggest **cheaper alternatives** for textbooks and platforms
- Provide **deterministic, straightforward suggestions** (no fancy language)
- Make it **easy to add/edit** course data later
- **Proactive assistance** - auto-suggests when detecting course names

---

## 📁 **Project Structure**

```
course-chatbot/
├── README.md                  # Full documentation (setup, API, troubleshooting)
├── DEPLOYMENT.md              # Production deployment guide (AWS, Docker)
├── PROJECT_SUMMARY.md         # This file - quick overview
├── setup.sh / setup.bat       # Automated setup scripts
├── .gitignore                 # Security - prevents committing secrets
│
├── backend/                   # Python Flask API
│   ├── app.py                 # Main Flask server (port 5001)
│   ├── suggestions.py         # CSV parsing & suggestion logic
│   ├── aws_bedrock.py         # AWS Bedrock integration (not active)
│   ├── web_search.py          # SerpAPI web search (optional)
│   ├── requirements.txt       # Python dependencies
│   ├── .env                   # Environment variables (API keys)
│   └── .env.example           # Template for credentials
│
├── frontend/                  # HTML/CSS/JavaScript
│   ├── chatbot-widget.html    # Standalone embeddable widget
│   ├── chatbot.js             # Frontend logic
│   └── demo.html              # Demo page with course form
│
└── data/
    └── previous_courses.csv   # Historical professor data (10 sample courses)
```

---

## ✅ **What We've Built So Far**

### **1. Backend (Python Flask)**
- ✅ Flask API server running on **port 5001** (changed from 5000 due to macOS conflict)
- ✅ CSV data loading with **10 sample Foothill-De Anza courses**:
  - BIOL 10 (Biology)
  - MATH 1A (Calculus)
  - CS 1A (Programming)
  - ENGL 1A (English Composition)
  - CHEM 1A (Chemistry)
- ✅ Course name parsing (handles "Biology 10", "BIOL 10", "Introduction to Biology")
- ✅ Suggestion engine that **sorts by cost** (cheapest first)
- ✅ API endpoints:
  - `POST /api/suggestions` - Get course suggestions
  - `GET /api/health` - Health check
  - `GET /api/courses` - List all courses

### **2. Frontend (HTML/CSS/JS)**
- ✅ Bottom-right **floating chat button**
- ✅ Expandable chat window with professional UI
- ✅ **Auto-suggestion feature** - pops up when detecting course keywords
- ✅ Message bubbles (user vs bot)
- ✅ Typing indicators
- ✅ Suggestion display with:
  - 📚 Textbooks (title, cost, link)
  - 💻 Assignment Platforms (name, cost, link)
  - Cost highlighted (green for free, normal for paid)
- ✅ Demo page showing integration with course form

### **3. Data**
- ✅ 10 realistic Foothill-De Anza courses with:
  - Professor names
  - Course numbers (BIOL 10, MATH 1A, etc.)
  - Textbook titles, costs, URLs
  - Assignment platform names, costs, URLs
  - Cost range: $0 (OpenStax) to $320

### **4. Documentation**
- ✅ Comprehensive README.md (50+ sections)
- ✅ DEPLOYMENT.md (production guide)
- ✅ Setup scripts (Mac/Linux & Windows)
- ✅ Inline code comments

---

## ⚙️ **Current Configuration**

### **Backend Status:**
- **Port:** 5001 (changed from 5000 to avoid macOS AirPlay conflict)
- **Python Environment:** Virtual environment (venv)
- **Dependencies:** Flask, flask-cors (minimal - no AWS/AI currently)

### **API Keys Status:**
- ❌ **AWS Bedrock:** NOT configured (no IAM access to create keys)
- ✅ **SerpAPI:** Configured (you just added your key)
- Decision: **Running without AI** for now (CSV data only)

### **What Works Without AI:**
- ✅ Historical professor suggestions from CSV
- ✅ Sorted by cost (cheapest first)
- ✅ Full chatbot UI and interactions
- ✅ Auto-suggestions
- ❌ No AI-powered additional suggestions (acceptable)

---

## 🚀 **How to Run the Project**

### **Start Backend:**
```bash
cd course-chatbot/backend
source venv/bin/activate  # Activate virtual environment
python app.py             # Start server on port 5001
```

### **Open Frontend:**
```bash
cd course-chatbot/frontend
open demo.html            # Or double-click the file
```

### **Test:**
1. Click blue chat button (bottom-right)
2. Type: "Biology 10" or "BIOL 10"
3. See suggestions appear!

---

## 📝 **Sample Data in CSV**

The chatbot currently knows about these courses:

| Course | Textbook Options | Cost Range | Platform Options |
|--------|-----------------|------------|-----------------|
| BIOL 10 | Campbell Biology, OpenStax | $0 - $145 | Mastering Biology, Top Hat |
| MATH 1A | Stewart Calculus, OpenStax | $0 - $280 | WebAssign, MyOpenMath |
| CS 1A | Starting Out with Python, Python Crash Course | $40 - $135 | Zybooks, Replit |
| ENGL 1A | Norton Field Guide, They Say I Say | $65 - $85 | Canvas, Turnitin |
| CHEM 1A | Chemistry: Central Science, OpenStax | $0 - $320 | Mastering Chemistry, ALEKS |

---

## 🔑 **Environment Variables (.env file)**

Located at: `course-chatbot/backend/.env`

```bash
FLASK_ENV=development

# SerpAPI (for web search)
SERPAPI_API_KEY=your_actual_key_here  # ✅ You added this!

# AWS Bedrock (for AI suggestions - NOT configured)
# AWS_REGION=us-east-1
# AWS_ACCESS_KEY_ID=
# AWS_SECRET_ACCESS_KEY=
```

---

## 🛠️ **How to Add New Course Data**

1. **Open CSV:**
   ```bash
   nano course-chatbot/data/previous_courses.csv
   ```

2. **Add a new line:**
   ```csv
   Dr. New Professor,Course Name,COURSE 123,CRN,01,Textbook Title,99,https://url,Platform Name,50,https://url
   ```

3. **Restart backend:**
   ```bash
   # Ctrl+C to stop, then:
   python app.py
   ```

4. **Test in chatbot!**

---

## 🔗 **Integration with Your Team's Python App**

Your teammate can integrate this chatbot in 3 ways:

### **Option 1: Embed HTML Widget**
Copy the chatbot HTML/JS into their existing form pages.

### **Option 2: Use API Directly**
```python
import requests
response = requests.post('http://localhost:5001/api/suggestions', 
                        json={'query': 'Biology 10'})
suggestions = response.json()
```

### **Option 3: Import Suggestion Engine**
```python
from suggestions import SuggestionEngine
engine = SuggestionEngine()
results = engine.get_csv_suggestions(course_info)
```

---

## ⚠️ **Known Issues & Solutions**

### **Issue 1: Port 5000 Already in Use**
- **Cause:** macOS AirPlay Receiver uses port 5000
- **Solution:** Changed to port 5001 ✅
- **Files updated:** `app.py`, `chatbot.js`

### **Issue 2: No AWS IAM Access**
- **Cause:** You don't have permissions to create IAM users
- **Solution:** Running without AI suggestions (CSV only) ✅
- **Alternative:** Could add OpenAI API later (easier to get keys)

### **Issue 3: SerpAPI Key Configuration**
- **Cause:** Placeholder text was detected as valid key
- **Solution:** Fixed validation logic in `web_search.py` ✅
- **Status:** You've now added a real SerpAPI key ✅

---

## 🎯 **Next Steps (When You Continue)**

### **Immediate:**
1. ✅ Start backend with your SerpAPI key
2. ✅ Test web search suggestions (should work now!)
3. ⬜ Add real Foothill-De Anza course data to CSV
4. ⬜ Test with various course queries

### **Short-term:**
5. ⬜ Integrate chatbot into your teammate's Python form app
6. ⬜ Customize colors to match Foothill-De Anza branding
7. ⬜ Add more courses to CSV database
8. ⬜ Test with real professors (get feedback)

### **Future (Optional):**
9. ⬜ Get AWS Bedrock access for AI suggestions
10. ⬜ Migrate CSV to PostgreSQL database
11. ⬜ Deploy to production (AWS or college servers)
12. ⬜ Add authentication for admin features
13. ⬜ Integration with Banner (course catalog system)

---

## 📚 **Key Files to Remember**

| File | Purpose | When to Edit |
|------|---------|-------------|
| `backend/app.py` | Flask server | Change ports, add endpoints |
| `backend/suggestions.py` | Suggestion logic | Modify search/filter logic |
| `backend/.env` | API keys | Add credentials |
| `frontend/chatbot.js` | Frontend logic | Change behavior, API URL |
| `frontend/demo.html` | Demo page | Test integration |
| `data/previous_courses.csv` | Course data | Add new courses |

---

## 💡 **Important Commands**

```bash
# Start backend
cd course-chatbot/backend
source venv/bin/activate
python app.py

# Test API
curl http://localhost:5001/api/health
curl -X POST http://localhost:5001/api/suggestions \
  -H "Content-Type: application/json" \
  -d '{"query": "Biology 10"}'

# Edit CSV data
nano course-chatbot/data/previous_courses.csv

# Edit environment variables
nano course-chatbot/backend/.env

# View backend logs
# Just watch the terminal where python app.py is running
```

---

## 🎨 **Customization Guide**

### **Change Chatbot Colors:**
Edit `frontend/chatbot-widget.html` or `demo.html`:
```css
#chatbot-button {
  background: linear-gradient(135deg, #0066cc, #004d99);
  /* Change to Foothill colors */
}
```

### **Change Auto-Suggestion Trigger:**
Edit `frontend/chatbot.js` (line 38):
```javascript
if (value.length > 3) {  // Change to 5 for longer trigger
```

### **Add Course Keywords:**
Edit `frontend/chatbot.js` (line 40):
```javascript
const courseKeywords = ['biol', 'math', 'chem', 'your-new-keyword'];
```

---

## 🆘 **Troubleshooting Quick Reference**

| Problem | Solution |
|---------|----------|
| Port already in use | Changed to 5001 (already done) |
| Backend won't start | Check if venv is activated |
| No suggestions appear | Check course name matches CSV data |
| API connection failed | Ensure backend is running on 5001 |
| Changes not showing | Restart backend, refresh browser |
| CSV not loading | Check file path, encoding (UTF-8) |

---

## 📞 **When You Return to This Project**

### **To Resume Work:**

1. **Read this summary** (you're here! ✅)
2. **Start backend:**
   ```bash
   cd course-chatbot/backend
   source venv/bin/activate
   python app.py
   ```
3. **Open demo:**
   ```bash
   open course-chatbot/frontend/demo.html
   ```
4. **Ask me to continue** and share:
   - What you want to add/change
   - Any errors you're seeing
   - Your progress on data collection

### **Questions to Ask Me:**

- "How do I add 50 courses to the CSV at once?"
- "Can you help integrate this with my teammate's Python app?"
- "How do I change the chatbot colors to match our college?"
- "Can you add OpenAI instead of AWS Bedrock?"
- "How do I deploy this to a production server?"
- "Can you help me migrate from CSV to a real database?"

---

## ✅ **Current Status Summary**

**✅ Completed:**
- Project structure created
- Backend API working (port 5001)
- Frontend chatbot widget working
- 10 sample courses loaded
- SerpAPI configured
- Documentation complete
- Demo page ready

**⏸️ On Hold:**
- AWS Bedrock integration (no IAM access)
- AI-powered suggestions (decided to skip for now)

**📋 Ready for Next Phase:**
- Adding real course data
- Integration with teammate's app
- Customization and testing
- Production deployment (when ready)

---

## 🎉 **Success Metrics**

When the project is fully deployed, you'll have:

- ✅ A chatbot professors can use on the course form
- ✅ Suggestions based on real historical data
- ✅ Cost-focused recommendations (free options highlighted)
- ✅ Easy-to-update course database (CSV or DB)
- ✅ Reduced stress for new professors
- ✅ Potential cost savings for students

---

## 📄 **Additional Resources**

- **Full Documentation:** `README.md` (comprehensive setup guide)
- **Deployment Guide:** `DEPLOYMENT.md` (AWS, Docker, production)
- **Setup Scripts:** `setup.sh` (Mac) or `setup.bat` (Windows)
- **API Documentation:** See README.md sections on API endpoints

---

**Last Updated:** [Date you created this]
**Created By:** AI Assistant + Nyi Htet
**Purpose:** Help Foothill-De Anza professors find affordable course materials

---

## 💾 **Backup Instructions**

Before making major changes:

```bash
# Backup the entire project
cd ..
cp -r course-chatbot course-chatbot-backup

# Or backup just the data
cp course-chatbot/data/previous_courses.csv previous_courses_backup.csv

# Or use Git (recommended)
cd course-chatbot
git init
git add .
git commit -m "Initial working version"
```

---

**🚀 You're all set!** Save this document and refer back to it when you continue the project. Good luck with the chatbot! 🎓

