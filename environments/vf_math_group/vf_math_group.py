import verifiers as vf
from verifiers.utils.data_utils import extract_boxed_answer, load_example_dataset


def load_environment(**kwargs):
    system_prompt = """
    Think step-by-step inside <think>...</think> tags.

    Then, give your final numerical answer inside \\boxed{{...}}.
    """

    parser = vf.ThinkParser(extract_fn=extract_boxed_answer)

    # env 1: gsm8k
    def gsm8k_answer_reward_func(completion, answer, **kwargs):
        response = parser.parse_answer(completion) or ""
        return 1.0 if response == answer else 0.0

    rubric1 = vf.Rubric(
        funcs=[gsm8k_answer_reward_func, parser.get_format_reward_func()],
        weights=[1.0, 0.2],
    )
    dataset1 = load_example_dataset("gsm8k", split="train").select(range(1000))
    env1 = vf.SingleTurnEnv(
        dataset=dataset1,
        system_prompt=system_prompt,
        parser=parser,
        rubric=rubric1,
    )

    # env 2: math
    def math_answer_reward_func(completion, answer, **kwargs):
        response = parser.parse_answer(completion) or ""
        return 1.0 if response == answer else 0.0

    rubric2 = vf.Rubric(
        funcs=[math_answer_reward_func, parser.get_format_reward_func()],
        weights=[1.0, 0.2],
    )
    dataset2 = load_example_dataset("math", split="train").select(range(1000))
    env2 = vf.SingleTurnEnv(
        dataset=dataset2,
        system_prompt=system_prompt,
        parser=parser,
        rubric=rubric2,
    )

    vf_env = vf.EnvGroup([env1, env2], env_names=["gsm8k", "math"])
    return vf_env
