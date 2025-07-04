"""Pytest configuration and fixtures for verifiers tests."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datasets import Dataset
from verifiers.parsers import Parser, XMLParser, ThinkParser
from verifiers.envs import Environment, SingleTurnEnv, MultiTurnEnv
from verifiers.rubrics import Rubric


@pytest.fixture
def basic_parser():
    """Return a basic Parser instance."""
    return Parser()


@pytest.fixture
def xml_parser():
    """Return an XMLParser instance with common fields."""
    return XMLParser(
        fields=["reasoning", "answer"],
        answer_field="answer"
    )


@pytest.fixture
def xml_parser_with_alternatives():
    """Return an XMLParser instance with alternative field names."""
    return XMLParser(
        fields=["reasoning", ("code", "answer")],
        answer_field="answer"
    )


@pytest.fixture
def think_parser():
    """Return a ThinkParser instance."""
    return ThinkParser()


@pytest.fixture
def think_parser_with_extractor():
    """Return a ThinkParser instance with custom extraction function."""
    def extract_boxed(text):
        """Simple boxed answer extractor for testing."""
        import re
        match = re.search(r'\\boxed\{([^}]+)\}', text)
        return match.group(1) if match else text
    
    return ThinkParser(extract_fn=extract_boxed)


# Async test fixtures for Environment testing

class MockAsyncOpenAI:
    """Mock AsyncOpenAI client that maps conversation inputs to outputs."""
    
    def __init__(self):
        self.chat_completions = {}  # Maps conversation history to responses
        self.text_completions = {}  # Maps prompts to responses
        self.default_chat_response = "This is a test response"
        self.default_text_response = "This is a test completion"
        self.base_url = "http://localhost/v1/"  # For testing URL parsing
        
        # Create mock structure
        self.chat = MagicMock()
        self.completions = MagicMock()
        self.chat.completions = MagicMock()
        
        # Set up async methods
        self.chat.completions.create = AsyncMock(side_effect=self._handle_chat_completion)
        self.completions.create = MagicMock(side_effect=self._handle_text_completion)
    
    def add_chat_response(self, messages, response, finish_reason="stop"):
        """Add a mapped response for specific messages."""
        # Convert messages to a hashable key
        key = self._messages_to_key(messages)
        self.chat_completions[key] = {
            "content": response,
            "finish_reason": finish_reason
        }
    
    def add_text_response(self, prompt, response, finish_reason="stop"):
        """Add a mapped response for specific prompt."""
        self.text_completions[prompt] = {
            "text": response,
            "finish_reason": finish_reason
        }
    
    def set_default_responses(self, chat_response=None, text_response=None):
        """Set default responses when no mapping found."""
        if chat_response:
            self.default_chat_response = chat_response
        if text_response:
            self.default_text_response = text_response
    
    async def _handle_chat_completion(self, messages, **kwargs):
        """Handle chat completion requests."""
        key = self._messages_to_key(messages)
        
        if key in self.chat_completions:
            response_data = self.chat_completions[key]
        else:
            response_data = {
                "content": self.default_chat_response,
                "finish_reason": "stop"
            }
        
        # Create mock response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = response_data["content"]
        mock_response.choices[0].finish_reason = response_data["finish_reason"]
        return mock_response
    
    def _handle_text_completion(self, prompt, **kwargs):
        """Handle text completion requests."""
        if prompt in self.text_completions:
            response_data = self.text_completions[prompt]
        else:
            response_data = {
                "text": self.default_text_response,
                "finish_reason": "stop"
            }
        
        # Create mock response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].text = response_data["text"]
        mock_response.choices[0].finish_reason = response_data["finish_reason"]
        return mock_response
    
    def _messages_to_key(self, messages):
        """Convert messages list to a hashable key."""
        # Create a simplified representation for hashing
        key_parts = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            key_parts.append(f"{role}:{content}")
        return tuple(key_parts)


@pytest.fixture
def mock_openai_client():
    """Return a mocked AsyncOpenAI client with input-output mapping."""
    return MockAsyncOpenAI()


@pytest.fixture 
def sample_dataset():
    """Return a sample dataset for testing."""
    return Dataset.from_dict({
        "question": ["What is 2+2?", "What is the capital of France?"],
        "answer": ["4", "Paris"]
    })


@pytest.fixture
def sample_chat_dataset():
    """Return a sample dataset with chat format."""
    return Dataset.from_dict({
        "prompt": [
            [{"role": "user", "content": "What is 2+2?"}],
            [{"role": "user", "content": "What is the capital of France?"}]
        ],
        "answer": ["4", "Paris"]
    })


@pytest.fixture
def mock_singleturn_env(mock_openai_client, sample_dataset):
    """Return a SingleTurnEnv with mocked client and dataset."""
    return SingleTurnEnv(
        client=mock_openai_client,
        model="test-model",
        dataset=sample_dataset,
        system_prompt="You are a helpful assistant.",
        parser=Parser(),
        rubric=Rubric()
    )


@pytest.fixture
def mock_singleturn_env_completion(mock_openai_client):
    """Return a SingleTurnEnv for completion format testing."""
    completion_dataset = Dataset.from_dict({
        "prompt": ["Calculate 2+2:", "Name the capital of France:"],
        "answer": ["4", "Paris"]
    })
    return SingleTurnEnv(
        client=mock_openai_client,
        model="test-model", 
        dataset=completion_dataset,
        message_type="completion",
        parser=Parser(),
        rubric=Rubric()
    )


# MultiTurnEnv test fixtures

class SimpleMultiTurnEnv(MultiTurnEnv):
    """Simple concrete implementation of MultiTurnEnv for testing."""
    
    def __init__(self, completion_condition="answer", **kwargs):
        super().__init__(**kwargs)
        self.completion_condition = completion_condition  # "answer", "max_turns", "error"
        self.env_response_count = 0
    
    def is_completed(self, messages, state, **kwargs):
        """Simple completion logic for testing."""
        if self.completion_condition == "answer":
            # Complete when assistant says "DONE"
            if messages and messages[-1].get("role") == "assistant":
                return "DONE" in messages[-1].get("content", "")
        elif self.completion_condition == "max_turns":
            # Never complete naturally (test max_turns)
            return False
        elif self.completion_condition == "error":
            # Complete on any error
            if messages and messages[-1].get("role") == "assistant":
                return messages[-1].get("content", "").startswith("[ERROR]")
        return False
    
    def env_response(self, messages, state, **kwargs):
        """Simple environment response for testing."""
        self.env_response_count += 1
        
        if self.completion_condition == "answer":
            # Encourage completion after a few turns
            if self.env_response_count >= 2:
                return {"role": "user", "content": "Please finish with DONE"}, state
            else:
                return {"role": "user", "content": f"Continue (turn {self.env_response_count})"}, state
        else:
            return {"role": "user", "content": f"Environment response {self.env_response_count}"}, state


@pytest.fixture
def mock_multiturn_env(mock_openai_client, sample_chat_dataset):
    """Return a MultiTurnEnv for basic testing."""
    return SimpleMultiTurnEnv(
        client=mock_openai_client,
        model="test-model",
        dataset=sample_chat_dataset,
        max_turns=3,
        completion_condition="answer",
        parser=Parser(),
        rubric=Rubric()
    )


@pytest.fixture  
def mock_multiturn_env_max_turns(mock_openai_client, sample_chat_dataset):
    """Return a MultiTurnEnv that tests max_turns limiting."""
    return SimpleMultiTurnEnv(
        client=mock_openai_client,
        model="test-model",
        dataset=sample_chat_dataset,
        max_turns=2,
        completion_condition="max_turns",  # Never complete naturally
        parser=Parser(),
        rubric=Rubric()
    )