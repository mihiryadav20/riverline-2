"""
Test script for Gemini API integration
This file tests if the GEMINI_API_KEY is working correctly.
"""

import os
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables
load_dotenv()

def test_gemini_api():
    """Test the Gemini API with a simple prompt."""

    # Get API key from environment
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        print("❌ ERROR: GEMINI_API_KEY not found in .env file")
        return False

    try:
        # Validate API key format
        if not api_key.startswith("AIza"):
            print("❌ ERROR: Invalid API key format. Gemini API keys should start with 'AIza'")
            return False

        print(f"🔑 API Key loaded (length: {len(api_key)} characters)")

        # Configure the API
        genai.configure(api_key=api_key)

        # List available models for debugging
        print("🔍 Checking available models...")
        try:
            models = genai.list_models()
            available_models = [model.name for model in models if 'generateContent' in model.supported_generation_methods]
            print(f"📋 Available models with generateContent: {available_models}")
            if not available_models:
                print("❌ No models support generateContent method")
                return False
        except Exception as list_error:
            print(f"⚠️  Could not list models: {list_error}")
            return False

        # Use the first available model
        model_name = available_models[0] if available_models else 'gemini-pro'
        print(f"🎯 Using model: {model_name}")

        # Create a model instance
        model = genai.GenerativeModel(model_name)

        # Test with a simple prompt
        prompt = "Hello! Please introduce yourself in one sentence."

        print("🔄 Testing Gemini API...")
        print(f"📝 Prompt: {prompt}")
        print()

        # Generate response
        response = model.generate_content(prompt)

        print("✅ SUCCESS: Gemini API is working!")
        print(f"🤖 Gemini Response: {response.text}")
        print()

        return True

    except Exception as e:
        print(f"❌ ERROR: Failed to use Gemini API: {str(e)}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("GEMINI API TEST")
    print("=" * 60)
    print()

    success = test_gemini_api()

    print("=" * 60)
    if success:
        print("🎉 TEST PASSED: Gemini API key is valid and working")
    else:
        print("💥 TEST FAILED: Check your API key and internet connection")
    print("=" * 60)
