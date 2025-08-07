import verifiers as vf


def load_environment(
    use_diamond: bool = True, use_think: bool = True
) -> vf.Environment:
    from verifiers.utils.data_utils import load_example_dataset

    if use_diamond:
        eval_dataset = load_example_dataset("gpqa_diamond", "train")
    else:
        eval_dataset = load_example_dataset("gpqa_main", "train")
    if use_think:
        system_prompt = """Think step-by-step inside <think>...</think> tags, then give only the letter of the correct answer."""
        parser = vf.ThinkParser()
    else:
        system_prompt = """Give only the letter of the correct answer. /no_think"""
        parser = vf.Parser()

    def correct_answer_reward_func(completion, answer, **kwargs) -> float:
        response = parser.parse_answer(completion) or ""
        return 1.0 if response.startswith(str(answer)) else 0.0

    rubric = vf.Rubric(funcs=[correct_answer_reward_func], weights=[1.0])
    vf_env = vf.SingleTurnEnv(
        eval_dataset=eval_dataset,
        system_prompt=system_prompt,
        parser=parser,
        rubric=rubric,
    )
    return vf_env
