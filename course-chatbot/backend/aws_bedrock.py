"""
AWS Bedrock Integration for AI-Powered Suggestions
Uses Claude Sonnet for generating textbook and platform recommendations
"""

import boto3
import json
import os
from typing import Dict, Optional

class BedrockAI:
    def __init__(self):
        """
        Initialize AWS Bedrock client
        Requires AWS credentials to be configured
        """
        try:
            self.bedrock_runtime = boto3.client(
                service_name='bedrock-runtime',
                region_name=os.getenv('AWS_REGION', 'us-east-1')
            )
            self.model_id = 'anthropic.claude-3-5-sonnet-20241022-v2:0'
            print("✓ AWS Bedrock client initialized")
        except Exception as e:
            print(f"⚠ Warning: Could not initialize AWS Bedrock client: {str(e)}")
            self.bedrock_runtime = None
    
    def get_textbook_suggestion(self, course_info: Dict) -> Optional[Dict]:
        """
        Get one additional textbook suggestion using Claude
        Returns deterministic answer with title, price, and URL
        """
        if not self.bedrock_runtime:
            return None
        
        try:
            prompt = f"""You are helping professors find affordable textbook alternatives for their courses.

Course: {course_info['display_name']} ({course_info.get('original_query', '')})

Task: Suggest ONE affordable textbook or open educational resource (OER) for this course.

Requirements:
- Must be a legitimate, well-reviewed resource
- Prefer open-source/free options or significantly cheaper alternatives
- Must be appropriate for community college level
- Provide exact title, approximate cost, and a real URL

Return your answer in this exact JSON format (no extra text):
{{
    "title": "Exact Book Title",
    "cost": 0 or numeric value,
    "url": "https://..."
}}"""

            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 500,
                "temperature": 0.3,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            })
            
            response = self.bedrock_runtime.invoke_model(
                modelId=self.model_id,
                body=body
            )
            
            response_body = json.loads(response['body'].read())
            response_text = response_body['content'][0]['text']
            
            # Parse JSON from response
            suggestion = self._parse_json_response(response_text)
            
            if suggestion and 'title' in suggestion and 'cost' in suggestion and 'url' in suggestion:
                print(f"✓ AI Suggestion: {suggestion['title']} - ${suggestion['cost']}")
                return suggestion
            
            return None
            
        except Exception as e:
            print(f"⚠ Error getting AI suggestion: {str(e)}")
            return None
    
    def validate_platform(self, platform_name: str, course_level: str) -> Dict:
        """
        Validate if a platform is good for a specific course level
        Returns validation result with reasoning
        """
        if not self.bedrock_runtime:
            return {
                'is_valid': True,
                'reason': 'Could not validate (AWS not configured)'
            }
        
        try:
            prompt = f"""Is {platform_name} a good assignment platform for {course_level} level courses?

Respond in this JSON format:
{{
    "is_valid": true or false,
    "reason": "brief one-sentence reason"
}}"""

            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 200,
                "temperature": 0.1,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            })
            
            response = self.bedrock_runtime.invoke_model(
                modelId=self.model_id,
                body=body
            )
            
            response_body = json.loads(response['body'].read())
            response_text = response_body['content'][0]['text']
            
            validation = self._parse_json_response(response_text)
            
            if validation:
                return validation
            
            return {'is_valid': True, 'reason': 'Could not parse validation'}
            
        except Exception as e:
            print(f"⚠ Error validating platform: {str(e)}")
            return {'is_valid': True, 'reason': 'Validation error'}
    
    def _parse_json_response(self, text: str) -> Optional[Dict]:
        """
        Parse JSON from Claude's response
        Handles cases where Claude includes extra text
        """
        try:
            # Try direct JSON parse
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            import re
            json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(1))
            
            # Try to find JSON object in text
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            
            return None


# Standalone testing
if __name__ == '__main__':
    print("Testing AWS Bedrock Integration...")
    print("=" * 60)
    
    ai = BedrockAI()
    
    if ai.bedrock_runtime:
        # Test textbook suggestion
        test_course = {
            'department': 'BIOL',
            'number': '10',
            'display_name': 'Introduction to Biology',
            'original_query': 'Biology 10'
        }
        
        print("\nTesting AI Textbook Suggestion...")
        suggestion = ai.get_textbook_suggestion(test_course)
        
        if suggestion:
            print(f"Title: {suggestion['title']}")
            print(f"Cost: ${suggestion['cost']}")
            print(f"URL: {suggestion['url']}")
        else:
            print("No suggestion returned")
        
        # Test platform validation
        print("\nTesting Platform Validation...")
        validation = ai.validate_platform("Mastering Biology", "introductory")
        print(f"Valid: {validation['is_valid']}")
        print(f"Reason: {validation['reason']}")
    else:
        print("AWS Bedrock not configured - skipping tests")
    
    print("\n" + "=" * 60)
