"""Tests for the base Environment class."""

from unittest.mock import AsyncMock, Mock

import pytest
from datasets import Dataset

from verifiers import Environment, Parser, Rubric
from verifiers.types import GenerateOutputs, RolloutScores


# Create a concrete implementation for testing the abstract base class
class SimpleEnvironment(Environment):
    """Simple implementation of Environment for testing."""

    async def rollout(
        self,
        client,
        model,
        prompt,
        answer="",
        task="default",
        info={},
        sampling_args={},
        **kwargs,
    ):
        """Simple test rollout implementation."""
        response = await self.get_model_response(
            prompt=prompt, client=client, model=model, sampling_args=sampling_args
        )
        if self.message_type == "chat":
            completion = [
                {"role": "assistant", "content": response.choices[0].message.content}
            ]
            state = {"responses": [response]}
        else:
            completion = response.choices[0].text
            state = {}
        return completion, state


class TestEnvironmentBase:
    """Test cases for the base Environment class."""

    def test_environment_initialization(self, mock_openai_client, sample_dataset):
        """Test that Environment initializes correctly."""
        env = SimpleEnvironment(
            client=mock_openai_client,
            model="test-model",
            dataset=sample_dataset,
            parser=Parser(),
            rubric=Rubric(),
        )
        assert env.client == mock_openai_client
        assert env.model == "test-model"
        assert env.message_type == "chat"
        assert isinstance(env.parser, Parser)
        assert isinstance(env.rubric, Rubric)

    def test_environment_with_eval_dataset_only(
        self, mock_openai_client, sample_dataset
    ):
        """Test Environment with only eval_dataset."""
        env = SimpleEnvironment(
            client=mock_openai_client,
            model="test-model",
            eval_dataset=sample_dataset,
            parser=Parser(),
            rubric=Rubric(),
        )
        assert env.dataset is None
        assert env.eval_dataset is not None

    def test_environment_no_datasets_raises_error(self, mock_openai_client):
        """Test that Environment raises error when no datasets provided."""
        with pytest.raises(
            ValueError, match="Either dataset or eval_dataset must be provided"
        ):
            SimpleEnvironment(
                client=mock_openai_client,
                model="test-model",
                parser=Parser(),
                rubric=Rubric(),
            )

    def test_completion_mode_with_system_prompt_raises_error(
        self, mock_openai_client, sample_dataset
    ):
        """Test that completion mode with system prompt raises error."""
        with pytest.raises(ValueError, match="not supported for completion tasks"):
            SimpleEnvironment(
                client=mock_openai_client,
                model="test-model",
                dataset=sample_dataset,
                message_type="completion",
                system_prompt="test prompt",
                parser=Parser(),
                rubric=Rubric(),
            )

    def test_format_prompt(self, mock_openai_client, sample_dataset):
        """Test prompt formatting."""
        env = SimpleEnvironment(
            client=mock_openai_client,
            model="test-model",
            dataset=sample_dataset,
            parser=Parser(),
            rubric=Rubric(),
        )

        prompt = "What is 2+2?"
        system_prompt = "You are a helpful assistant."
        few_shot = [
            {"role": "user", "content": "What is 1+1?"},
            {"role": "assistant", "content": "2"},
        ]

        formatted = env.format_prompt(prompt, system_prompt, few_shot)

        assert len(formatted) == 4
        assert formatted[0]["role"] == "system"
        assert formatted[0]["content"] == system_prompt
        assert formatted[1]["role"] == "user"
        assert formatted[1]["content"] == "What is 1+1?"
        assert formatted[2]["role"] == "assistant"
        assert formatted[2]["content"] == "2"
        assert formatted[3]["role"] == "user"
        assert formatted[3]["content"] == prompt

    def test_get_dataset(self, mock_openai_client, sample_dataset):
        """Test dataset retrieval."""
        env = SimpleEnvironment(
            client=mock_openai_client,
            model="test-model",
            dataset=sample_dataset,
            parser=Parser(),
            rubric=Rubric(),
        )

        # Get full dataset
        full_dataset = env.get_dataset()
        assert len(full_dataset) == 2

        # Get subset
        subset = env.get_dataset(n=1)
        assert len(subset) == 1

    @pytest.mark.asyncio
    async def test_get_model_response_chat(self, mock_openai_client):
        """Test get_model_response with chat format."""
        env = SimpleEnvironment(
            client=mock_openai_client,
            model="test-model",
            eval_dataset=Dataset.from_dict({"question": ["test"], "answer": ["test"]}),
            parser=Parser(),
            rubric=Rubric(),
        )

        prompt = [{"role": "user", "content": "Hello"}]
        response = await env.get_model_response(
            prompt=prompt,
            client=mock_openai_client,
            model="test-model",
            message_type="chat",
        )

        # Check response structure
        assert hasattr(response, "choices")
        assert len(response.choices) > 0
        assert hasattr(response.choices[0], "message")
        assert hasattr(response.choices[0].message, "content")
        mock_openai_client.chat.completions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_model_response_completion(self, mock_openai_client):
        """Test get_model_response with completion format."""
        env = SimpleEnvironment(
            client=mock_openai_client,
            model="test-model",
            eval_dataset=Dataset.from_dict({"prompt": ["test"], "answer": ["test"]}),
            message_type="completion",
            parser=Parser(),
            rubric=Rubric(),
        )

        prompt = "Complete this:"
        response = await env.get_model_response(
            prompt=prompt,
            client=mock_openai_client,
            model="test-model",
            message_type="completion",
        )

        # Check response structure
        assert hasattr(response, "choices")
        assert len(response.choices) > 0
        assert hasattr(response.choices[0], "text")
        mock_openai_client.completions.create.assert_called_once()

    def test_process_chat_format(self, mock_openai_client, sample_dataset):
        """Test processing chat format conversations."""
        env = SimpleEnvironment(
            client=mock_openai_client,
            model="test-model",
            dataset=sample_dataset,
            parser=Parser(),
            rubric=Rubric(),
        )

        # Create a mock tokenizer
        mock_tokenizer = Mock()
        mock_tokenizer.apply_chat_template = Mock(
            side_effect=lambda messages,
            tokenize=False,
            add_generation_prompt=True: "User: What is 2+2?Assistant:"
            if add_generation_prompt
            else "User: What is 2+2?Assistant: 4"
        )
        mock_tokenizer.encode = Mock(
            side_effect=lambda text: list(range(len(text.split())))
        )

        prompt = [{"role": "user", "content": "What is 2+2?"}]
        completion = [{"role": "assistant", "content": "4"}]

        prompt_ids, prompt_mask, completion_ids, completion_mask = (
            env.process_chat_format(
                prompt, completion, mock_tokenizer, mask_env_responses=False
            )
        )

        assert isinstance(prompt_ids, list)
        assert isinstance(prompt_mask, list)
        assert isinstance(completion_ids, list)
        assert isinstance(completion_mask, list)
        assert len(prompt_ids) == len(prompt_mask)
        assert len(completion_ids) == len(completion_mask)
        assert all(m == 0 for m in prompt_mask)  # Prompt mask should be all 0s
        assert all(m == 1 for m in completion_mask)  # Completion mask should be all 1s

    def test_process_completion_format(self, mock_openai_client, sample_dataset):
        """Test processing completion format text."""
        env = SimpleEnvironment(
            client=mock_openai_client,
            model="test-model",
            dataset=sample_dataset,
            parser=Parser(),
            rubric=Rubric(),
        )

        # Create a mock tokenizer
        mock_tokenizer = Mock()
        mock_tokenizer.encode = Mock(side_effect=lambda text: list(range(len(text))))

        prompt = "Complete this: 2+2="
        completion = "4"

        prompt_ids, prompt_mask, completion_ids, completion_mask = (
            env.process_completion_format(prompt, completion, mock_tokenizer)
        )

        assert isinstance(prompt_ids, list)
        assert isinstance(prompt_mask, list)
        assert isinstance(completion_ids, list)
        assert isinstance(completion_mask, list)
        assert len(prompt_ids) == len(prompt)
        assert len(completion_ids) == len(completion)
        assert all(m == 0 for m in prompt_mask)
        assert all(m == 1 for m in completion_mask)

    def test_process_env_results_chat(self, mock_openai_client, sample_dataset):
        """Test processing environment results for chat format."""
        env = SimpleEnvironment(
            client=mock_openai_client,
            model="test-model",
            dataset=sample_dataset,
            parser=Parser(),
            rubric=Rubric(),
        )

        # Create a mock tokenizer
        mock_tokenizer = Mock()

        # Track the conversation state
        def mock_apply_chat_template(
            conversation, tokenize=False, add_generation_prompt=True
        ):
            # Convert messages to a string representation
            text = ""
            for msg in conversation:
                text += f"{msg['role']}: {msg['content']} "
            return text.strip()

        def mock_encode(text, **kwargs):
            # Return tokens based on the text content
            if "assistant: Hi there!" in text:
                # Prompt + completion: return extended tokens
                return [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
            elif "user: Hello" in text:
                # Just prompt: return base tokens
                return [1, 2, 3, 4, 5]
            else:
                # Default case
                return [1, 2, 3]

        mock_tokenizer.apply_chat_template = Mock(side_effect=mock_apply_chat_template)
        mock_tokenizer.encode = Mock(side_effect=mock_encode)

        prompts = [[{"role": "user", "content": "Hello"}]]
        completions = [[{"role": "assistant", "content": "Hi there!"}]]
        states = [{}]
        rewards = [1.0]

        results = env.process_env_results(
            prompts, completions, states, rewards, mock_tokenizer
        )

        assert hasattr(results, "prompt_ids")
        assert hasattr(results, "prompt_mask")
        assert hasattr(results, "completion_ids")
        assert hasattr(results, "completion_mask")
        assert hasattr(results, "completion_logprobs")
        assert hasattr(results, "rewards")
        assert len(results.rewards) == 1
        assert results.rewards[0] == 1.0

    def test_process_env_results_with_truncation(
        self, mock_openai_client, sample_dataset
    ):
        """Test processing environment results with sequence length truncation."""
        env = SimpleEnvironment(
            client=mock_openai_client,
            model="test-model",
            dataset=sample_dataset,
            parser=Parser(),
            rubric=Rubric(),
        )

        # Create a mock tokenizer
        mock_tokenizer = Mock()

        # Track the conversation state
        def mock_apply_chat_template(
            conversation, tokenize=False, add_generation_prompt=True
        ):
            # Convert messages to a string representation
            text = ""
            for msg in conversation:
                text += f"{msg['role']}: {msg['content']} "
            return text.strip()

        def mock_encode(text, **kwargs):
            # Return tokens based on the text content
            if "assistant: Hi there!" in text:
                # Prompt + completion: return extended tokens
                return [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
            elif "user: Hello" in text:
                # Just prompt: return base tokens
                return [1, 2, 3, 4, 5]
            else:
                # Default case
                return [1, 2, 3]

        mock_tokenizer.apply_chat_template = Mock(side_effect=mock_apply_chat_template)
        mock_tokenizer.encode = Mock(side_effect=mock_encode)

        prompts = [[{"role": "user", "content": "Hello"}]]
        completions = [[{"role": "assistant", "content": "Hi there!"}]]
        states = [{}]
        rewards = [1.0]

        results = env.process_env_results(
            prompts,
            completions,
            states,
            rewards,
            mock_tokenizer,
            max_seq_len=8,  # Force truncation
            mask_truncated_completions=True,
        )

        # Check that total length respects max_seq_len
        total_len = len(results.prompt_ids[0]) + len(results.completion_ids[0])
        assert total_len <= 8
        # Check that truncated completion is masked
        assert all(m == 0 for m in results.completion_mask[0])

    def test_parse_chat_completion_logprobs(self, mock_openai_client, sample_dataset):
        """Test parsing logprobs from a vLLM chat completion."""
        env = SimpleEnvironment(
            client=mock_openai_client,
            model="test-model",
            dataset=sample_dataset,
            parser=Parser(),
            rubric=Rubric(),
        )

        # Create mock chat completion with logprobs
        mock_completion = Mock()
        mock_completion.choices = [Mock()]
        mock_completion.choices[0].logprobs = Mock()
        mock_completion.choices[0].logprobs.content = [
            Mock(logprob=-0.5),
            Mock(logprob=-1.2),
            Mock(logprob=-0.3),
        ]

        logprobs = env.parse_chat_completion_logprobs(mock_completion)
        assert logprobs == [-0.5, -1.2, -0.3]

    def test_parse_chat_completion_tokens(self, mock_openai_client, sample_dataset):
        """Test parsing tokens from a vLLM chat completion."""
        env = SimpleEnvironment(
            client=mock_openai_client,
            model="test-model",
            dataset=sample_dataset,
            parser=Parser(),
            rubric=Rubric(),
        )

        # Create mock chat completion with tokens
        mock_completion = Mock()
        mock_completion.choices = [Mock()]
        mock_completion.choices[0].logprobs = Mock()
        mock_completion.choices[0].logprobs.content = [
            Mock(token="id:1234"),
            Mock(token="id:5678"),
            Mock(token="id:9012"),
        ]

        tokens = env.parse_chat_completion_tokens(mock_completion)
        assert tokens == [1234, 5678, 9012]

    @pytest.mark.asyncio
    async def test_run_rollouts(self, mock_openai_client):
        """Test running multiple rollouts."""
        env = SimpleEnvironment(
            client=mock_openai_client,
            model="test-model",
            eval_dataset=Dataset.from_dict({"question": ["test"], "answer": ["test"]}),
            parser=Parser(),
            rubric=Rubric(),
        )

        prompts = [
            [{"role": "user", "content": "Hello"}],
            [{"role": "user", "content": "Hi"}],
        ]
        answers = ["response1", "response2"]
        tasks = ["default", "default"]
        infos = [{}, {}]

        # Mock the rollout method calls
        results = await env.run_rollouts(
            client=mock_openai_client,
            model="test-model",
            prompts=prompts,
            answers=answers,
            tasks=tasks,
            infos=infos,
        )

        assert len(results) == 2
        assert all(
            len(result) == 2 for result in results
        )  # Each result is (completion, state)

    @pytest.mark.asyncio
    async def test_a_generate_with_score_rollouts(
        self, mock_openai_client, sample_dataset
    ):
        """Test async generate with scoring enabled."""
        env = SimpleEnvironment(
            client=mock_openai_client,
            model="test-model",
            dataset=sample_dataset,
            parser=Parser(),
            rubric=Rubric(),
        )

        # Mock the rubric scoring
        env.rubric.score_rollouts = AsyncMock(
            return_value=RolloutScores(reward=[1.0], metrics={})
        )

        inputs = {"prompt": [[{"role": "user", "content": "Hello"}]], "answer": ["Hi"]}

        results = await env.a_generate(inputs, score_rollouts=True)

        assert hasattr(results, "completion")
        assert hasattr(results, "state")
        assert hasattr(results, "reward")
        assert results.reward == [1.0]

    def test_generate_sync_wrapper(self, mock_openai_client, sample_dataset):
        """Test synchronous generate wrapper."""
        env = SimpleEnvironment(
            client=mock_openai_client,
            model="test-model",
            dataset=sample_dataset,
            parser=Parser(),
            rubric=Rubric(),
        )

        # Mock the rubric scoring
        env.rubric.score_rollouts = AsyncMock(
            return_value=RolloutScores(reward=[1.0], metrics={})
        )

        inputs = {"prompt": [[{"role": "user", "content": "Hello"}]], "answer": ["Hi"]}

        results = env.generate(inputs, client=env.client)

        assert hasattr(results, "completion")
        assert hasattr(results, "state")
        assert hasattr(results, "reward")

    def test_make_dataset(self, mock_openai_client, sample_dataset):
        """Test creating a dataset from evaluation results."""
        env = SimpleEnvironment(
            client=mock_openai_client,
            model="test-model",
            dataset=sample_dataset,
            parser=Parser(),
            rubric=Rubric(),
        )

        results = GenerateOutputs(
            prompt=[[{"role": "user", "content": "Hello"}]],
            completion=[[{"role": "assistant", "content": "Hi"}]],
            answer=["Hi"],
            reward=[1.0],
            task=["default"],
            state=[{"custom_field": "value"}],
            info=[{}],
            metrics={},
        )

        dataset = env.make_dataset(results, state_columns=["custom_field"])

        assert len(dataset) == 1
        assert "prompt" in dataset.column_names
        assert "completion" in dataset.column_names
        assert "answer" in dataset.column_names
        assert "reward" in dataset.column_names
        assert "task" in dataset.column_names
        assert "custom_field" in dataset.column_names
