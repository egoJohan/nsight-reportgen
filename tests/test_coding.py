import pandas as pd
from nsight.coding import top_words


def test_top_words_normalizes_and_counts():
    frame = pd.DataFrame({"w1": ["Kallis", "kallis ", "Luotettava", "KALLIS", "hyvä"],
                          "w2": ["luotettava", None, "kallis", None, None]})
    res = top_words(frame, text_vars=["w1", "w2"], top_n=2)
    assert res[0] == ("kallis", 4)
    assert res[1] == ("luotettava", 2)


def test_top_words_respects_top_n():
    frame = pd.DataFrame({"w": ["a", "a", "b", "c"]})
    assert len(top_words(frame, text_vars=["w"], top_n=1)) == 1
