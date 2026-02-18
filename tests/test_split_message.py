"""split_message 유틸 함수 단위 테스트."""

from secretary.platforms.telegram_bot import TELEGRAM_MAX_LENGTH, split_message


class TestSplitMessageShortText:
    """max_length 이하 텍스트는 분할하지 않는다."""

    def test_short_text_returns_single_chunk(self):
        text = "짧은 메시지"
        result = split_message(text)
        assert result == [text]

    def test_empty_string(self):
        result = split_message("")
        assert result == [""]

    def test_exact_limit(self):
        text = "a" * TELEGRAM_MAX_LENGTH
        result = split_message(text)
        assert result == [text]


class TestSplitMessageParagraphs:
    """빈 줄(문단) 경계로 분할한다."""

    def test_splits_at_paragraph_boundary(self):
        """문단 경계(\n\n)에서 분할하며, 구분자는 앞 청크에 포함된다."""
        para1 = "가" * 3000
        para2 = "나" * 3000
        text = f"{para1}\n\n{para2}"
        result = split_message(text)
        assert len(result) == 2
        # \n\n 구분자는 앞 청크에 포함됨 (세그먼트 합치기 로직)
        assert result[0] == para1 + "\n\n"
        assert result[1] == para2

    def test_multiple_paragraphs_merged_when_possible(self):
        """여러 짧은 문단은 하나의 청크로 합친다."""
        paras = ["짧은 문단입니다."] * 5
        text = "\n\n".join(paras)
        result = split_message(text)
        assert len(result) == 1
        assert result[0] == text

    def test_three_paragraphs_split_as_needed(self):
        para1 = "가" * 2000
        para2 = "나" * 2000
        para3 = "다" * 2000
        text = f"{para1}\n\n{para2}\n\n{para3}"
        result = split_message(text)
        # para1(2000) + \n\n(2) + para2(2000) = 4002 <= 4096 -> 합쳐짐
        # + \n\n(2) + para3(2000) = 6004 > 4096 -> 분할
        assert len(result) == 2
        for chunk in result:
            assert len(chunk) <= TELEGRAM_MAX_LENGTH


class TestSplitMessageCodeBlocks:
    """코드 블록 경계를 존중한다."""

    def test_code_block_kept_intact(self):
        intro = "코드 예시입니다:"
        code = '```python\nprint("hello")\n```'
        outro = "위 코드를 실행하세요."
        text = f"{intro}\n\n{code}\n\n{outro}"
        result = split_message(text)
        assert len(result) == 1  # 전체가 4096 이내
        assert '```python\nprint("hello")\n```' in result[0]

    def test_code_block_not_split_in_middle(self):
        """코드 블록이 다른 문단과 합쳐져서 초과할 때, 코드 블록 자체는 깨지지 않는다."""
        # 3800자 인트로 + 코드블록 = 4096 초과하도록 설정
        long_intro = "가" * 3800
        code = "```python\n" + "x = 1\n" * 100 + "```"
        text = f"{long_intro}\n\n{code}"
        result = split_message(text)
        assert len(result) >= 2
        # 코드 블록이 포함된 청크에서 ```가 올바르게 열리고 닫히는지 확인
        for chunk in result:
            if "```python" in chunk:
                assert chunk.count("```") % 2 == 0  # 짝수개 (열고 닫기)

    def test_oversized_code_block_split_at_lines(self):
        """코드 블록 자체가 4096자를 초과하면 줄 단위로 분할하되 마커를 보존한다."""
        # 각 줄을 충분히 길게 만들어 전체가 4096자를 확실히 초과하도록 함
        lines = [f"line_{i} = " + "'x' * 80  # padding" for i in range(300)]
        code = "```python\n" + "\n".join(lines) + "\n```"
        assert len(code) > TELEGRAM_MAX_LENGTH

        result = split_message(code)
        assert len(result) >= 2
        for chunk in result:
            assert chunk.startswith("```python\n")
            assert chunk.endswith("```")
            assert len(chunk) <= TELEGRAM_MAX_LENGTH


class TestSplitMessageLineFallback:
    """문단/코드블록 분할로 부족할 때 줄 단위로 분할한다."""

    def test_single_huge_paragraph_split_at_lines(self):
        """빈 줄 없이 줄바꿈만 있는 긴 텍스트를 줄 단위로 분할한다."""
        lines = [f"줄번호 {i}: " + "가" * 80 for i in range(100)]
        text = "\n".join(lines)
        assert len(text) > TELEGRAM_MAX_LENGTH

        result = split_message(text)
        assert len(result) >= 2
        for chunk in result:
            assert len(chunk) <= TELEGRAM_MAX_LENGTH

    def test_all_chunks_within_limit(self):
        """줄바꿈이 없는 긴 텍스트도 모든 청크가 max_length 이하여야 한다."""
        text = "가나다라마바사" * 1000
        result = split_message(text, max_length=100)
        for chunk in result:
            assert len(chunk) <= 100

    def test_no_newline_text_split_by_chars(self):
        """줄바꿈이 전혀 없는 긴 텍스트는 문자 단위로 분할한다."""
        text = "A" * 10000
        result = split_message(text)
        assert len(result) >= 3  # 10000 / 4096 = 최소 3개
        for chunk in result:
            assert len(chunk) <= TELEGRAM_MAX_LENGTH
        # 합치면 원본 복원
        assert "".join(result) == text

    def test_concatenation_preserves_content(self):
        """분할 후 합치면 원본 텍스트가 복원되어야 한다."""
        para1 = "가" * 3000
        para2 = "나" * 3000
        text = f"{para1}\n\n{para2}"
        result = split_message(text)
        assert "".join(result) == text


class TestSplitMessageCustomMaxLength:
    """max_length 파라미터 동작 확인."""

    def test_custom_max_length(self):
        text = "Hello World! " * 10  # 130 chars, 줄바꿈 없음
        result = split_message(text, max_length=50)
        assert len(result) >= 2
        for chunk in result:
            assert len(chunk) <= 50

    def test_mixed_content_with_small_limit(self):
        text = "제목\n\n```python\nprint('hi')\n```\n\n마무리"
        result = split_message(text, max_length=30)
        assert len(result) >= 2
        for chunk in result:
            assert len(chunk) <= 30
