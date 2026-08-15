from analysis import analyse, ghost_marks, is_no_op, strip_marks, word_diff


# Each fixture reproduces a real failure, with the wording replaced by
# synthetic text. Only the subject matter is invented: every marked span,
# every misspelling and every corrected word sits where it did in the
# original, so the word alignment these tests pin down is unchanged.

# The model claimed "have decided" needed the past participle. It already
# was one: nothing in the correction differs from the original.
ID13_PROMPT = "Remind me what we have decided about the demo catalogue. I still see Northwind and Kestrel with autosuggestions"
ID13_CORRECTION = 'Remind me what we have <mark data-type="grammar">decided</mark> about the demo catalogue. I still see Northwind and Kestrel with autosuggestions'

# Two genuine fixes plus one invented: the article was said to be missing
# in "both occurrences", but the first occurrence already had it.
ID14_PROMPT = "Look at the entry above (the one about the demo catalogue). It looks as if it is a false positive. I asked another model and it confirmed that but also suggested that in this situation they'd rather use past simple instead of present perfect. So why falce positive and how can I get suggestions like that?"
ID14_CORRECTION = 'Look at the entry above (the one about the demo catalogue). It looks as if it is <mark data-type="grammar">a</mark> false positive. I asked another model and it confirmed that but also suggested that in this situation they\'d rather use past simple instead of present perfect. So why <mark data-type="grammar">a</mark> <mark data-type="spelling">false</mark> positive and how can I get suggestions like that?'

# Four genuine fixes plus one invented "the". This is the case that
# distinguishes per-span alignment from a blanket "correction == original"
# rule: the correction really does differ, in four other places.
ID32_PROMPT = "Write down a note to discuss: I want to mark (one by one) items as approved, which means they need to get a mark in the left panel (check/uncheck) so I can see which are unapproved + a zero-size (if absent) adjutment as I did before. This should be possible only if all entries in item are approved.\n+ Uncheck marks in all items in one button (could ebe at the very bottom)"
ID32_CORRECTION = 'Write down a note to discuss: I want to mark (one by one) items as approved, which means they need to get a mark in the left panel (check/uncheck) so I can see which are unapproved + a zero-size (if absent) <mark data-type="spelling">adjustment</mark> as I did before. This should be possible only if all entries in <mark data-type="grammar">an item</mark> are approved.\n+ Uncheck marks in all items <mark data-type="word-choice">with</mark> one button (could <mark data-type="spelling">be</mark> at <mark data-type="grammar">the</mark> very bottom)'

# Every mark is a real change. The detector must stay silent here.
CLEAN_PROMPT = "3. We need to take into account the seasonal variation and look to the last 3 years\nLooking at the rest right away"
CLEAN_CORRECTION = '3. We need to take into account the seasonal variation and look <mark data-type="grammar">at</mark> the last 3 years\nLooking at the rest right away'


def test_whole_correction_changed_nothing():
    assert is_no_op(ID13_PROMPT, ID13_CORRECTION) is True
    ghosts = ghost_marks(ID13_PROMPT, ID13_CORRECTION)
    assert [g["text"] for g in ghosts] == ["decided"]
    assert ghosts[0]["type"] == "grammar"


def test_one_ghost_among_two_real_fixes():
    ghosts = ghost_marks(ID14_PROMPT, ID14_CORRECTION)
    assert [g["text"] for g in ghosts] == ["a"]
    # The *first* "a" is the invented one; the second really was inserted.
    stripped, _ = strip_marks(ID14_CORRECTION)
    assert stripped[: ghosts[0]["offset"]].endswith("as if it is ")


def test_one_ghost_among_four_real_fixes():
    # The case a blanket "nothing changed" rule would miss entirely.
    assert is_no_op(ID32_PROMPT, ID32_CORRECTION) is False
    ghosts = ghost_marks(ID32_PROMPT, ID32_CORRECTION)
    assert [g["text"] for g in ghosts] == ["the"]


def test_genuine_correction_reports_no_ghosts():
    # More important than any positive case: a detector that cries wolf on
    # good results is worse than no detector.
    assert ghost_marks(CLEAN_PROMPT, CLEAN_CORRECTION) == []
    assert is_no_op(CLEAN_PROMPT, CLEAN_CORRECTION) is False


def test_deleted_word_leaves_its_neighbour_marked_not_ghosted():
    # "discuss about" -> "discuss". The deletion removes the only wrong word,
    # so the model has nothing to wrap but the survivor next to the gap.
    assert (
        ghost_marks(
            "we need to discuss about the issue",
            'we need to <mark data-type="grammar">discuss</mark> the issue',
        )
        == []
    )


def test_deleted_word_leaves_the_word_after_it_marked_not_ghosted():
    assert (
        ghost_marks(
            "I have has decided",
            'I have <mark data-type="grammar">decided</mark>',
        )
        == []
    )


def test_a_mark_away_from_the_deletion_is_still_a_ghost():
    # The border rule must forgive the neighbours of a deletion, not the whole
    # correction that contains one.
    ghosts = ghost_marks(
        "we need to discuss about the issue today",
        'we need to discuss the <mark data-type="grammar">issue</mark> today',
    )
    assert [g["text"] for g in ghosts] == ["issue"]


def test_multi_word_mark_unchanged_is_a_ghost():
    assert [g["text"] for g in ghost_marks("a b c d", 'a <mark data-type="grammar">b c</mark> d')] == ["b c"]


def test_multi_word_mark_changed_is_not():
    assert ghost_marks("a b c d", 'a <mark data-type="grammar">B C</mark> d') == []


def test_adjacent_marks_judged_separately():
    ghosts = ghost_marks("cant go", '<mark data-type="grammar">can\'t</mark> <mark data-type="style">go</mark>')
    assert [g["text"] for g in ghosts] == ["go"]


def test_punctuation_inside_a_mark_counts_as_a_change():
    assert ghost_marks("hello world", '<mark data-type="grammar">hello,</mark> world') == []


def test_empty_correction_is_not_a_no_op():
    # No correction means the model reported nothing to fix, which is not the
    # same as claiming a fix that does nothing.
    assert analyse("some text", "") == {"no_op": False, "ghost_marks": [], "diff": []}


def test_correction_without_marks():
    assert ghost_marks("some text", "some other text") == []


def test_strip_marks_offsets_point_into_the_stripped_text():
    stripped, spans = strip_marks('a <mark data-type="spelling">B</mark> c')
    assert stripped == "a B c"
    assert spans[0]["offset"] == 2
    assert spans[0]["end"] == 3
    assert spans[0]["type"] == "spelling"
    assert stripped[spans[0]["offset"] : spans[0]["end"]] == "B"


def test_word_diff_reports_a_single_equal_run_when_nothing_changed():
    diff = word_diff(ID13_PROMPT, ID13_CORRECTION)
    assert [segment["op"] for segment in diff] == ["equal"]


def test_word_diff_names_each_real_change():
    diff = word_diff(ID32_PROMPT, ID32_CORRECTION)
    changes = [(s["op"], s["before"], s["after"]) for s in diff if s["op"] != "equal"]
    assert changes == [
        ("replace", "adjutment", "adjustment"),
        ("insert", "", "an"),
        ("replace", "in", "with"),
        ("replace", "ebe", "be"),
    ]
    # "the" is marked in the correction but appears in no change segment.
    assert all(s[2] != "the" for s in changes)


def test_analyse_bundles_the_three_reports():
    result = analyse(ID32_PROMPT, ID32_CORRECTION)
    assert result["no_op"] is False
    assert [g["text"] for g in result["ghost_marks"]] == ["the"]
    assert any(s["op"] == "replace" for s in result["diff"])


def test_diff_segments_carry_the_type_of_the_mark_they_fall_in():
    # The dashboard colours an insertion by the issue it fixes, so each changed
    # segment has to know which marked span it belongs to.
    diff = word_diff(ID32_PROMPT, ID32_CORRECTION)
    typed = {(s["after"], s["type"]) for s in diff if s["op"] != "equal"}
    assert ("adjustment", "spelling") in typed
    assert ("with", "word-choice") in typed
    # The mark spans "an account", but only "an" was inserted — the type comes
    # from the mark the segment falls inside, not from the segment's own text.
    assert ("an", "grammar") in typed


def test_equal_segments_carry_no_type():
    diff = word_diff(CLEAN_PROMPT, CLEAN_CORRECTION)
    assert all(s["type"] == "" for s in diff if s["op"] == "equal")


def test_a_deletion_carries_no_type():
    # On a deletion the model marks a surviving neighbour, never the removed
    # words, so there is no issue type to attribute to the removal itself.
    diff = word_diff(
        "we need to discuss about the issue",
        'we need to <mark data-type="grammar">discuss</mark> the issue',
    )
    deletions = [s for s in diff if s["op"] == "delete"]
    assert deletions and all(s["type"] == "" for s in deletions)


def test_diff_keeps_line_breaks_inside_a_segment():
    # The diff is what the dashboard renders now. Re-joining words with single
    # spaces turned a multi-paragraph correction into one run-on line.
    original = "first line here\nsecond line there"
    correction = (
        "first line here\nsecond line "
        '<mark data-type="grammar">everywhere</mark>'
    )
    diff = word_diff(original, correction)
    assert "\n" in diff[0]["before"]
    assert "\n" in diff[0]["after"]


def test_a_line_break_between_segments_survives_as_a_separator():
    # The break falls between two segments rather than inside one, which is
    # where re-joining with single spaces used to swallow it.
    original = "make it red\n2. what happens here"
    correction = (
        'make it <mark data-type="word-choice">crimson</mark>'
        "\n2. what happens here"
    )
    diff = word_diff(original, correction)
    changed = next(i for i, s in enumerate(diff) if s["op"] != "equal")
    assert "\n" in diff[changed]["sep"]
    # Reassembling from the segments reproduces the corrected text exactly.
    rebuilt = "".join(s["after"] + s["sep"] for s in diff)
    assert rebuilt == "make it crimson\n2. what happens here"
