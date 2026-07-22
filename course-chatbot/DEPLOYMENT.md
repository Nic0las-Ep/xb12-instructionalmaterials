# Deployment Guide
## Course Materials Chatbot - Production Deployment

---

## 🎯 Overview

This guide covers deploying the Course Materials Chatbot to a production environment for use by Foothill-De Anza faculty.

---

## 🏢 Deployment Options

### Option 1: AWS (Recommended)

**Architecture:**
- **Backend:** AWS Elastic Beanstalk or EC2
- **Frontend:** S3 + CloudFront
- **Database:** RDS (PostgreSQL) or keep CSV on S3
- **AI:** AWS Bedrock (already integrated)

**Advantages:**
- Native Bedrock integration
- Scalable and reliable
- Cost-effective for college workload

### Option 2: Traditional Server

**Architecture:**
- **Backend:** Linux server (Ubuntu/CentOS) with Python
- **Frontend:** Nginx serving static files
- **Database:** PostgreSQL on same server or separate
- **AI:** AWS Bedrock via API

**Advantages:**
- Full control
- No vendor lock-in
- Can use existing infrastructure

### Option 3: Container-based (Docker)

**Architecture:**
- **Backend:** Docker container with Flask
- **Frontend:** Nginx container
- **Orchestration:** Docker Compose or Kubernetes
- **Hosting:** AWS ECS, DigitalOcean, or on-premise

**Advantages:**
- Portable
- Easy to update
- Consistent environments

---

## 🚀 AWS Deployment (Step-by-Step)

### Prerequisites

- AWS Account with admin access
- AWS CLI installed and configured
- Domain name (optional but recommended)

### Step 1: Prepare Backend for AWS

Create `course-chatbot/backend/application.py`:

```python
# AWS Elastic Beanstalk entry point
from app import app as application

if __name__ == '__main__':
    application.run()
```

Create `course-chatbot/backend/.ebextensions/python.config`:

```yaml
option_settings:
  aws:elasticbeanstalk:container:python:
    WSGIPath: application:application
  aws:elasticbeanstalk:application:environment:
    FLASK_ENV: production
```

### Step 2: Deploy Backend to Elastic Beanstalk

```bash
# Install EB CLI
pip install awsebcli

# Initialize EB application
cd backend
eb init -p python-3.9 course-chatbot-backend --region us-west-2

# Create environment and deploy
eb create course-chatbot-production

# Set environment variables
eb setenv AWS_REGION=us-east-1 \
          AWS_ACCESS_KEY_ID=your_key \
          AWS_SECRET_ACCESS_KEY=your_secret \
          SERPAPI_API_KEY=your_key

# Deploy updates
eb deploy
```

### Step 3: Deploy Frontend to S3

```bash
# Create S3 bucket
aws s3 mb s3://course-chatbot-frontend

# Enable static website hosting
aws s3 website s3://course-chatbot-frontend \
    --index-document demo.html

# Upload files
cd frontend
aws s3 sync . s3://course-chatbot-frontend --acl public-read

# Update API URL in chatbot.js before uploading
# Change: const API_BASE_URL = 'http://your-eb-url.elasticbeanstalk.com/api';
```

### Step 4: Configure CloudFront (Optional)

- Create CloudFront distribution
- Point to S3 bucket
- Enable HTTPS with ACM certificate
- Set custom domain (e.g., chatbot.fhda.edu)

### Step 5: Update CORS Settings

In `backend/app.py`:

```python
CORS(app, origins=[
    'https://your-cloudfront-domain.cloudfront.net',
    'https://chatbot.fhda.edu'  # Your custom domain
])
```

---

## 🐳 Docker Deployment

### Create Dockerfile for Backend

Create `course-chatbot/backend/Dockerfile`:

```dockerfile
FROM python:3.9-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Expose port
EXPOSE 5000

# Run application
CMD ["python", "app.py"]
```

### Create Dockerfile for Frontend

Create `course-chatbot/frontend/Dockerfile`:

```dockerfile
FROM nginx:alpine

# Copy frontend files
COPY . /usr/share/nginx/html

# Copy nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
```

### Create Docker Compose

Create `course-chatbot/docker-compose.yml`:

```yaml
version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "5000:5000"
    environment:
      - AWS_REGION=${AWS_REGION}
      - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
      - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
      - SERPAPI_API_KEY=${SERPAPI_API_KEY}
    volumes:
      - ./data:/app/data
    restart: unless-stopped

  frontend:
    build: ./frontend
    ports:
      - "80:80"
    depends_on:
      - backend
    restart: unless-stopped
```

### Deploy with Docker

```bash
# Build and start
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

---

## 🗄️ Database Migration (CSV to PostgreSQL)

For production, consider migrating from CSV to PostgreSQL:

### Step 1: Create Database Schema

```sql
CREATE TABLE courses (
    id SERIAL PRIMARY KEY,
    professor_name VARCHAR(255),
    class_name VARCHAR(255),
    course_number VARCHAR(50),
    crn_code VARCHAR(50),
    section VARCHAR(50),
    textbook_title TEXT,
    textbook_cost DECIMAL(10, 2),
    textbook_url TEXT,
    platform_name VARCHAR(255),
    platform_cost DECIMAL(10, 2),
    platform_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_course_number ON courses(course_number);
```

### Step 2: Migrate Data

```python
# migration_script.py
import csv
import psycopg2
from psycopg2.extras import execute_values

conn = psycopg2.connect(
    host="your-rds-endpoint.amazonaws.com",
    database="course_chatbot",
    user="admin",
    password="your-password"
)

with open('../data/previous_courses.csv', 'r') as f:
    reader = csv.DictReader(f)
    data = [(
        row['professor_name'],
        row['class_name'],
        row['course_number'],
        row['crn_code'],
        row['section'],
        row['textbook_title'],
        float(row['textbook_cost']),
        row['textbook_url'],
        row['platform_name'],
        float(row['platform_cost']),
        row['platform_url']
    ) for row in reader]

with conn.cursor() as cur:
    execute_values(cur, """
        INSERT INTO courses (
            professor_name, class_name, course_number, crn_code,
            section, textbook_title, textbook_cost, textbook_url,
            platform_name, platform_cost, platform_url
        ) VALUES %s
    """, data)

conn.commit()
conn.close()
```

### Step 3: Update Backend Code

Modify `suggestions.py` to use PostgreSQL instead of CSV.

---

## 🔐 Production Security Checklist

- [ ] Use HTTPS everywhere (TLS/SSL certificates)
- [ ] Implement API rate limiting
- [ ] Add authentication for admin functions
- [ ] Use AWS IAM roles instead of access keys
- [ ] Enable AWS CloudTrail for audit logging
- [ ] Set up monitoring and alerting
- [ ] Implement CORS properly (restrict origins)
- [ ] Sanitize all user inputs
- [ ] Use environment variables for all secrets
- [ ] Enable Flask production mode (`FLASK_ENV=production`)
- [ ] Set up regular backups of course data
- [ ] Implement request logging
- [ ] Use CDN for frontend assets
- [ ] Enable DDoS protection (CloudFlare or AWS Shield)
- [ ] Regular security updates for dependencies

---

## 📊 Monitoring & Logging

### AWS CloudWatch

```python
# Add to app.py
import logging
from pythonjsonlogger import jsonlogger

logger = logging.getLogger()
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter()
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)
logger.setLevel(logging.INFO)

@app.route('/api/suggestions', methods=['POST'])
def get_suggestions():
    logger.info('Suggestion request received', extra={
        'query': request.json.get('query'),
        'ip': request.remote_addr
    })
    # ... rest of code
```

### Error Tracking

Consider integrating:
- **Sentry** for error tracking
- **AWS CloudWatch Logs** for centralized logging
- **Datadog** or **New Relic** for APM

---

## 🔄 CI/CD Pipeline

### GitHub Actions Example

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to AWS

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v2
    
    - name: Configure AWS credentials
      uses: aws-actions/configure-aws-credentials@v1
      with:
        aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
        aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
        aws-region: us-west-2
    
    - name: Deploy backend to Elastic Beanstalk
      run: |
        cd backend
        eb deploy course-chatbot-production
    
    - name: Deploy frontend to S3
      run: |
        cd frontend
        aws s3 sync . s3://course-chatbot-frontend
```

---

## 📈 Scaling Considerations

### Backend Scaling

- Use Elastic Beanstalk auto-scaling
- Configure based on CPU/memory usage
- Set min 2 instances for high availability

### Database Scaling

- Use RDS with read replicas
- Enable connection pooling
- Cache frequent queries with Redis

### Cost Optimization

- Use AWS Lambda for backend (serverless)
- Implement caching with CloudFront
- Use reserved instances for steady workload
- Monitor AWS costs with Cost Explorer

---

## 🧪 Production Testing

Before going live:

```bash
# Load testing
pip install locust

# Create locustfile.py
from locust import HttpUser, task, between

class ChatbotUser(HttpUser):
    wait_time = between(1, 3)
    
    @task
    def get_suggestions(self):
        self.client.post("/api/suggestions", json={
            "query": "Biology 10"
        })

# Run load test
locust -f locustfile.py --host=https://your-production-url.com
```

---

## 📱 Integration with College Systems

### Banner Integration

If using Ellucian Banner:

```python
# Add to suggestions.py
import cx_Oracle

def get_courses_from_banner():
    conn = cx_Oracle.connect(
        'user/password@banner-db-host:1521/PROD'
    )
    cursor = conn.cursor()
    cursor.execute("""
        SELECT SSBSECT_SUBJ_CODE, SSBSECT_CRSE_NUMB, 
               SSBSECT_SUBJ_CODE || ' ' || SSBSECT_CRSE_NUMB as course
        FROM SSBSECT
        WHERE SSBSECT_TERM_CODE = '202610'
    """)
    return cursor.fetchall()
```

### Canvas LMS Integration

Add as an LTI tool in Canvas for seamless faculty access.

---

## 🆘 Production Support

### Monitoring Dashboard

Set up a status page showing:
- API uptime
- Average response time
- Number of queries per day
- AWS Bedrock usage and costs
- SerpAPI quota remaining

### Support Contact

Provide faculty with:
- Help documentation link
- Support email
- IT helpdesk ticket system integration

---

## 📋 Go-Live Checklist

- [ ] Backend deployed and tested
- [ ] Frontend deployed and accessible
- [ ] HTTPS enabled with valid certificate
- [ ] Environment variables configured
- [ ] Database backup scheduled
- [ ] Monitoring and alerting active
- [ ] Error tracking configured
- [ ] Load testing completed
- [ ] Security scan completed
- [ ] CORS configured correctly
- [ ] Documentation updated
- [ ] Faculty training scheduled
- [ ] Support team briefed
- [ ] Rollback plan documented
- [ ] Launch communication sent

---

## 🔄 Maintenance Schedule

**Daily:**
- Check error logs
- Monitor API response times

**Weekly:**
- Review usage analytics
- Check AWS costs
- Update course data if needed

**Monthly:**
- Security updates
- Dependency updates
- Review and optimize costs

**Quarterly:**
- Major feature updates
- User feedback review
- Performance optimization

---

**Deployment Support:** Contact your IT department or AWS support for assistance.
