// Configuration
const API_BASE_URL = 'http://localhost:5001/api';

// State management
let chatState = {
    isOpen: false,
    lastCourseName: null,
    hasShownAutoSuggestion: false
};

// DOM Elements
const chatbotButton = document.getElementById('chatbot-button');
const chatbotWindow = document.getElementById('chatbot-window');
const closeButton = document.getElementById('close-button');
const messagesContainer = document.getElementById('chatbot-messages');
const inputField = document.getElementById('chatbot-input');
const sendButton = document.getElementById('send-button');

// Event Listeners
chatbotButton.addEventListener('click', toggleChat);
closeButton.addEventListener('click', toggleChat);
sendButton.addEventListener('click', sendMessage);
inputField.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        sendMessage();
    }
});

// Listen for course name input (for auto-suggestions)
inputField.addEventListener('input', handleInputChange);

// Toggle chat window
function toggleChat() {
    chatState.isOpen = !chatState.isOpen;
    chatbotWindow.classList.toggle('active');
    
    if (chatState.isOpen) {
        inputField.focus();
    }
}

// Handle input changes for auto-suggestions
function handleInputChange() {
    const value = inputField.value.trim();
    
    // Detect if user has typed a potential course name
    // Trigger auto-suggestion if input contains course keywords
    if (!chatState.hasShownAutoSuggestion && value.length > 3) {
        const courseKeywords = ['biol', 'math', 'chem', 'engl', 'cs', 'comp'];
        const hasKeyword = courseKeywords.some(keyword => 
            value.toLowerCase().includes(keyword)
        );
        
        if (hasKeyword) {
            chatState.hasShownAutoSuggestion = true;
            showAutoSuggestion(value);
        }
    }
}

// Show automatic suggestion
function showAutoSuggestion(courseName) {
    addBotMessage(
        `I noticed you're entering a course name. Would you like me to search for textbook and platform suggestions for "${courseName}"? Just press Send or modify the course name first.`
    );
}

// Send message
async function sendMessage() {
    const message = inputField.value.trim();
    
    if (!message) return;
    
    // Add user message
    addUserMessage(message);
    inputField.value = '';
    chatState.hasShownAutoSuggestion = false;
    
    // Show typing indicator
    const typingId = showTypingIndicator();
    
    // Disable input while processing
    inputField.disabled = true;
    sendButton.disabled = true;
    
    try {
        // Check if message is a course name or question
        const response = await fetchSuggestions(message);
        
        // Remove typing indicator
        removeTypingIndicator(typingId);
        
        // Display response
        if (response.type === 'suggestions') {
            displaySuggestions(response.data);
        } else if (response.type === 'message') {
            addBotMessage(response.message);
        } else if (response.type === 'error') {
            addBotMessage(response.message);
        }
    } catch (error) {
        removeTypingIndicator(typingId);
        addBotMessage('Sorry, I encountered an error. Please try again or contact support.');
        console.error('Error:', error);
    } finally {
        // Re-enable input
        inputField.disabled = false;
        sendButton.disabled = false;
        inputField.focus();
    }
}

// Fetch suggestions from backend
async function fetchSuggestions(query) {
    try {
        const response = await fetch(`${API_BASE_URL}/suggestions`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ query })
        });
        
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        
        return await response.json();
    } catch (error) {
        console.error('Fetch error:', error);
        return {
            type: 'error',
            message: 'Unable to connect to the server. Please make sure the backend is running.'
        };
    }
}

// Display suggestions
function displaySuggestions(data) {
    const { courseName, textbooks, platforms, aiSuggestion } = data;
    
    // Create intro message
    let introMessage = `Here are textbook and platform options for <strong>${courseName}</strong> based on previous professors:`;
    addBotMessage(introMessage);
    
    // Create suggestions container
    const suggestionsDiv = document.createElement('div');
    suggestionsDiv.className = 'suggestions-list';
    
    // Add textbooks section
    if (textbooks && textbooks.length > 0) {
        const textbookSection = document.createElement('div');
        textbookSection.innerHTML = '<div class="section-header">📚 Textbooks</div>';
        
        textbooks.forEach(book => {
            const item = document.createElement('div');
            item.className = 'suggestion-item';
            
            const cost = book.cost === 0 || book.cost === '0' ? 'Free' : `$${book.cost}`;
            const costColor = book.cost === 0 || book.cost === '0' ? '#28a745' : '#333';
            
            item.innerHTML = `
                <div class="suggestion-title">${book.title}</div>
                <div class="suggestion-details" style="color: ${costColor}; font-weight: 600;">${cost}</div>
                <a href="${book.url}" target="_blank" class="suggestion-link">View Resource →</a>
            `;
            
            textbookSection.appendChild(item);
        });
        
        suggestionsDiv.appendChild(textbookSection);
    }
    
    // Add platforms section
    if (platforms && platforms.length > 0) {
        const platformSection = document.createElement('div');
        platformSection.innerHTML = '<div class="section-header">💻 Assignment Platforms</div>';
        
        platforms.forEach(platform => {
            const item = document.createElement('div');
            item.className = 'suggestion-item';
            
            const cost = platform.cost === 0 || platform.cost === '0' ? 'Free' : `$${platform.cost}`;
            const costColor = platform.cost === 0 || platform.cost === '0' ? '#28a745' : '#333';
            
            item.innerHTML = `
                <div class="suggestion-title">${platform.name}</div>
                <div class="suggestion-details" style="color: ${costColor}; font-weight: 600;">${cost}</div>
                <a href="${platform.url}" target="_blank" class="suggestion-link">View Platform →</a>
            `;
            
            platformSection.appendChild(item);
        });
        
        suggestionsDiv.appendChild(platformSection);
    }
    
    // Add AI suggestion if available
    if (aiSuggestion) {
        const aiSection = document.createElement('div');
        aiSection.innerHTML = '<div class="section-header">🤖 Additional Suggestion</div>';
        
        const item = document.createElement('div');
        item.className = 'suggestion-item';
        item.style.background = '#f0f8ff';
        
        const cost = aiSuggestion.cost === 0 || aiSuggestion.cost === '0' || aiSuggestion.cost === 'Free' 
            ? 'Free' 
            : `$${aiSuggestion.cost}`;
        const costColor = cost === 'Free' ? '#28a745' : '#333';
        
        item.innerHTML = `
            <div class="suggestion-title">${aiSuggestion.title}</div>
            <div class="suggestion-details" style="color: ${costColor}; font-weight: 600;">${cost}</div>
            <a href="${aiSuggestion.url}" target="_blank" class="suggestion-link">View Resource →</a>
        `;
        
        aiSection.appendChild(item);
        suggestionsDiv.appendChild(aiSection);
    }
    
    // Add to messages
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message bot';
    messageDiv.appendChild(suggestionsDiv);
    messagesContainer.appendChild(messageDiv);
    
    scrollToBottom();
}

// Add user message
function addUserMessage(text) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message user';
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.textContent = text;
    
    messageDiv.appendChild(contentDiv);
    messagesContainer.appendChild(messageDiv);
    
    scrollToBottom();
}

// Add bot message
function addBotMessage(html) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message bot';
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.innerHTML = html;
    
    messageDiv.appendChild(contentDiv);
    messagesContainer.appendChild(messageDiv);
    
    scrollToBottom();
}

// Show typing indicator
function showTypingIndicator() {
    const typingDiv = document.createElement('div');
    typingDiv.className = 'message bot';
    typingDiv.id = 'typing-indicator';
    
    const indicator = document.createElement('div');
    indicator.className = 'typing-indicator';
    indicator.innerHTML = `
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
    `;
    
    typingDiv.appendChild(indicator);
    messagesContainer.appendChild(typingDiv);
    
    scrollToBottom();
    
    return 'typing-indicator';
}

// Remove typing indicator
function removeTypingIndicator(id) {
    const indicator = document.getElementById(id);
    if (indicator) {
        indicator.remove();
    }
}

// Scroll to bottom
function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// Initialize
console.log('Course Assistant Chatbot initialized');
