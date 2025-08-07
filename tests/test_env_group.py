"""Tests for the EnvGroup class."""

from unittest.mock import AsyncMock

import pytest
from datasets import Dataset

from verifiers import EnvGroup, Rubric, SingleTurnEnv
from verifiers.envs.env_group import EnvGroupRubric
from verifiers.types import RolloutScores


class TestEnvGroupRubric:
    """Test cases for the EnvGroupRubric class."""

    def test_env_group_rubric_initialization(self, mock_openai_client):
        """Test EnvGroupRubric initialization with multiple environments."""

        # Create test environments with different rubrics
        def func1(completion, **kwargs):
            return 1.0

        def func2(completion, **kwargs):
            return 0.5

        def func3(completion, **kwargs):
            return 0.8

        env1 = SingleTurnEnv(
            client=mock_openai_client,
            model="test-model",
            eval_dataset=Dataset.from_dict({"question": ["q1"], "answer": ["a1"]}),
            rubric=Rubric(funcs=[func1, func2], weights=[1.0, 0.5]),
        )

        env2 = SingleTurnEnv(
            client=mock_openai_client,
            model="test-model",
            eval_dataset=Dataset.from_dict({"question": ["q2"], "answer": ["a2"]}),
            rubric=Rubric(funcs=[func2, func3], weights=[0.7, 1.0]),
        )

        env_map = {"task1": env1, "task2": env2}
        rubric = EnvGroupRubric(env_map)

        assert rubric.env_map == env_map
        # Should have all unique reward function names
        assert set(rubric.all_reward_names) == {"func1", "func2", "func3"}

    @pytest.mark.asyncio
    async def test_env_group_rubric_score_rollout(self, mock_openai_client):
        """Test scoring a rollout with EnvGroupRubric."""

        # Create test environments
        def func1(completion, **kwargs):
            return 0.8

        def func2(completion, **kwargs):
            return 0.6

        env1 = SingleTurnEnv(
            client=mock_openai_client,
            model="test-model",
            eval_dataset=Dataset.from_dict({"question": ["q1"], "answer": ["a1"]}),
            rubric=Rubric(funcs=[func1], weights=[1.0]),
        )

        env2 = SingleTurnEnv(
            client=mock_openai_client,
            model="test-model",
            eval_dataset=Dataset.from_dict({"question": ["q2"], "answer": ["a2"]}),
            rubric=Rubric(funcs=[func2], weights=[1.0]),
        )

        env_map = {"math": env1, "code": env2}
        rubric = EnvGroupRubric(env_map)

        # Test scoring for "math" task
        result = await rubric.score_rollout(
            prompt="Test prompt",
            completion="Test completion",
            answer="Test answer",
            state={},
            task="math",
        )

        assert "func1" in result.metrics
        assert "func2" in result.metrics
        assert result.metrics["func1"] == 0.8  # From env1
        assert result.metrics["func2"] == 0.0  # Not in env1, so 0.0
        assert result.reward == 0.8

    @pytest.mark.asyncio
    async def test_env_group_rubric_unknown_task(self, mock_openai_client):
        """Test scoring with unknown task returns zeros."""
        env1 = SingleTurnEnv(
            client=mock_openai_client,
            model="test-model",
            eval_dataset=Dataset.from_dict({"question": ["q1"], "answer": ["a1"]}),
            rubric=Rubric(),
        )

        env_map = {"known_task": env1}
        rubric = EnvGroupRubric(env_map)

        result = await rubric.score_rollout(
            prompt="Test", completion="Test", task="unknown_task"
        )

        assert result.reward == 0.0


class TestEnvGroup:
    """Test cases for the EnvGroup class."""

    def test_env_group_initialization(self, mock_openai_client):
        """Test EnvGroup initialization with multiple environments."""
        env1 = SingleTurnEnv(
            client=mock_openai_client,
            model="test-model",
            dataset=Dataset.from_dict({"question": ["q1"], "answer": ["a1"]}),
            rubric=Rubric(),
        )

        env2 = SingleTurnEnv(
            client=mock_openai_client,
            model="test-model",
            dataset=Dataset.from_dict({"question": ["q2"], "answer": ["a2"]}),
            rubric=Rubric(),
        )

        env_group = EnvGroup(envs=[env1, env2])

        assert len(env_group.envs) == 2
        assert env_group.env_names == ["env_0", "env_1"]
        assert env_group.env_map["env_0"] == env1
        assert env_group.env_map["env_1"] == env2

    def test_env_group_with_custom_names(self, mock_openai_client):
        """Test EnvGroup with custom environment names."""
        env1 = SingleTurnEnv(
            client=mock_openai_client,
            model="test-model",
            dataset=Dataset.from_dict({"question": ["q1"], "answer": ["a1"]}),
            rubric=Rubric(),
        )

        env2 = SingleTurnEnv(
            client=mock_openai_client,
            model="test-model",
            dataset=Dataset.from_dict({"question": ["q2"], "answer": ["a2"]}),
            rubric=Rubric(),
        )

        env_group = EnvGroup(envs=[env1, env2], env_names=["math", "code"])

        assert env_group.env_names == ["math", "code"]
        assert env_group.env_map["math"] == env1
        assert env_group.env_map["code"] == env2

    def test_env_group_empty_envs_fails(self):
        """Test that EnvGroup fails with empty environments list."""
        with pytest.raises(
            ValueError, match="EnvGroup requires at least one environment"
        ):
            EnvGroup(envs=[])

    def test_env_group_mismatched_names_fails(self, mock_openai_client):
        """Test that EnvGroup fails when env_names length doesn't match envs."""
        env1 = SingleTurnEnv(
            client=mock_openai_client,
            model="test-model",
            eval_dataset=Dataset.from_dict({"question": ["q1"], "answer": ["a1"]}),
            rubric=Rubric(),
        )

        with pytest.raises(
            ValueError, match="Number of env_names must match number of envs"
        ):
            EnvGroup(envs=[env1], env_names=["math", "code"])

    def test_env_group_dataset_concatenation(self, mock_openai_client):
        """Test that EnvGroup properly concatenates datasets with task labels."""
        env1 = SingleTurnEnv(
            client=mock_openai_client,
            model="test-model",
            dataset=Dataset.from_dict(
                {"question": ["q1", "q2"], "answer": ["a1", "a2"]}
            ),
            rubric=Rubric(),
        )

        env2 = SingleTurnEnv(
            client=mock_openai_client,
            model="test-model",
            dataset=Dataset.from_dict({"question": ["q3"], "answer": ["a3"]}),
            rubric=Rubric(),
        )

        env_group = EnvGroup(envs=[env1, env2], env_names=["math", "code"])

        # Check concatenated dataset
        dataset = env_group.get_dataset()
        assert len(dataset) == 3
        assert "task" in dataset.column_names

        # Check task labels
        tasks = dataset["task"]
        assert tasks[0] == "math"
        assert tasks[1] == "math"
        assert tasks[2] == "code"

    def test_env_group_rubric_type(self, mock_openai_client):
        """Test that EnvGroup creates EnvGroupRubric."""
        env1 = SingleTurnEnv(
            client=mock_openai_client,
            model="test-model",
            dataset=Dataset.from_dict({"question": ["q1"], "answer": ["a1"]}),
            rubric=Rubric(),
        )

        env_group = EnvGroup(envs=[env1])

        assert isinstance(env_group.rubric, EnvGroupRubric)
        assert env_group.rubric.env_map["env_0"] == env1

    @pytest.mark.asyncio
    async def test_env_group_rollout_routing(self, mock_openai_client):
        """Test that rollout is properly routed to the correct sub-environment."""
        # Create environments with different behaviors
        env1 = SingleTurnEnv(
            client=mock_openai_client,
            model="test-model",
            dataset=Dataset.from_dict({"question": ["q1"], "answer": ["a1"]}),
            rubric=Rubric(),
        )

        env2 = SingleTurnEnv(
            client=mock_openai_client,
            model="test-model",
            dataset=Dataset.from_dict({"question": ["q2"], "answer": ["a2"]}),
            rubric=Rubric(),
        )

        # Mock the rollout methods to return different values
        env1.rollout = AsyncMock(return_value=("response1", {"env": "env1"}))
        env2.rollout = AsyncMock(return_value=("response2", {"env": "env2"}))

        env_group = EnvGroup(envs=[env1, env2], env_names=["math", "code"])

        # Test routing to math environment
        result1, state1 = await env_group.rollout(
            client=mock_openai_client,
            model="test-model",
            prompt="Test prompt",
            task="math",
        )

        assert result1 == "response1"
        assert state1["env"] == "env1"
        env1.rollout.assert_called_once()
        env2.rollout.assert_not_called()

        # Reset mocks
        env1.rollout.reset_mock()
        env2.rollout.reset_mock()

        # Test routing to code environment
        result2, state2 = await env_group.rollout(
            client=mock_openai_client,
            model="test-model",
            prompt="Test prompt",
            task="code",
        )

        assert result2 == "response2"
        assert state2["env"] == "env2"
        env1.rollout.assert_not_called()
        env2.rollout.assert_called_once()

    def test_get_env_for_task(self, mock_openai_client):
        """Test getting environment for a specific task."""
        env1 = SingleTurnEnv(
            client=mock_openai_client,
            model="test-model",
            dataset=Dataset.from_dict({"question": ["q1"], "answer": ["a1"]}),
            rubric=Rubric(),
        )

        env2 = SingleTurnEnv(
            client=mock_openai_client,
            model="test-model",
            dataset=Dataset.from_dict({"question": ["q2"], "answer": ["a2"]}),
            rubric=Rubric(),
        )

        env_group = EnvGroup(envs=[env1, env2], env_names=["math", "code"])

        assert env_group.get_env_for_task("math") == env1
        assert env_group.get_env_for_task("code") == env2
        # Unknown task returns first environment as fallback
        assert env_group.get_env_for_task("unknown") == env1

    @pytest.mark.asyncio
    async def test_env_group_generate(self, mock_openai_client):
        """Test generate method with EnvGroup."""
        env1 = SingleTurnEnv(
            client=mock_openai_client,
            model="test-model",
            dataset=Dataset.from_dict({"question": ["q1"], "answer": ["a1"]}),
            rubric=Rubric(),
        )

        env2 = SingleTurnEnv(
            client=mock_openai_client,
            model="test-model",
            dataset=Dataset.from_dict({"question": ["q2"], "answer": ["a2"]}),
            rubric=Rubric(),
        )

        env_group = EnvGroup(envs=[env1, env2], env_names=["math", "code"])

        # Mock the scoring
        env_group.rubric.score_rollouts = AsyncMock(
            return_value=RolloutScores(reward=[0.8, 0.9], metrics={})
        )

        inputs = {
            "prompt": [
                [{"role": "user", "content": "Math question"}],
                [{"role": "user", "content": "Code question"}],
            ],
            "answer": ["math_answer", "code_answer"],
            "task": ["math", "code"],
        }

        results = await env_group.a_generate(
            inputs, client=mock_openai_client, model="test-model"
        )

        assert hasattr(results, "completion")
        assert hasattr(results, "state")
        assert hasattr(results, "reward")
        assert len(results.completion) == 2

    def test_env_group_with_mixed_datasets(self, mock_openai_client):
        """Test EnvGroup with environments having different dataset configurations."""
        # Environment with both train and eval datasets
        env1 = SingleTurnEnv(
            client=mock_openai_client,
            model="test-model",
            dataset=Dataset.from_dict({"question": ["q1"], "answer": ["a1"]}),
            eval_dataset=Dataset.from_dict({"question": ["eq1"], "answer": ["ea1"]}),
            rubric=Rubric(),
        )

        # Environment with only eval dataset
        env2 = SingleTurnEnv(
            client=mock_openai_client,
            model="test-model",
            dataset=Dataset.from_dict({"question": ["q2"], "answer": ["a2"]}),
            eval_dataset=Dataset.from_dict({"question": ["eq2"], "answer": ["ea2"]}),
            rubric=Rubric(),
        )

        env_group = EnvGroup(envs=[env1, env2], env_names=["task1", "task2"])

        # Should have concatenated train dataset from both envs
        train_dataset = env_group.get_dataset()
        assert len(train_dataset) == 2
        assert train_dataset["task"][0] == "task1"
        assert train_dataset["task"][1] == "task2"

        # Should have concatenated eval datasets from both
        eval_dataset = env_group.get_eval_dataset()
        assert len(eval_dataset) == 2
        assert eval_dataset["task"][0] == "task1"
        assert eval_dataset["task"][1] == "task2"
