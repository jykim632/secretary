"""_strip_html 유틸리티 함수 테스트."""

from secretary.agent.tools.search_tools import _strip_html


def test_removes_script_tags():
    """script 태그와 내용이 완전히 제거되는지 확인."""
    html = '<p>Hello</p><script>alert("xss")</script><p>World</p>'
    result = _strip_html(html)
    assert "alert" not in result
    assert "script" not in result
    assert "Hello" in result
    assert "World" in result


def test_removes_style_tags():
    """style 태그와 내용이 완전히 제거되는지 확인."""
    html = "<p>Hello</p><style>body { color: red; }</style><p>World</p>"
    result = _strip_html(html)
    assert "color" not in result
    assert "style" not in result
    assert "Hello" in result
    assert "World" in result


def test_removes_html_tags():
    """일반 HTML 태그가 제거되는지 확인."""
    html = "<h1>Title</h1><p>Paragraph</p><a href='url'>Link</a>"
    result = _strip_html(html)
    assert "<" not in result
    assert ">" not in result
    assert "Title" in result
    assert "Paragraph" in result
    assert "Link" in result


def test_removes_html_comments():
    """HTML 주석이 제거되는지 확인."""
    html = "<p>Before</p><!-- This is a comment --><p>After</p>"
    result = _strip_html(html)
    assert "comment" not in result
    assert "Before" in result
    assert "After" in result


def test_decodes_html_entities():
    """HTML 엔티티가 올바르게 변환되는지 확인."""
    html = "<p>&amp; &lt; &gt; &quot; &#39; &nbsp;</p>"
    result = _strip_html(html)
    assert "&" in result
    assert "<" in result
    assert ">" in result
    assert '"' in result
    assert "'" in result


def test_collapses_whitespace():
    """연속 공백이 정리되는지 확인."""
    html = "<p>Hello</p>   \n\n\n   <p>World</p>"
    result = _strip_html(html)
    # 연속 줄바꿈은 최대 2개로 정리
    assert "\n\n\n" not in result
    assert "Hello" in result
    assert "World" in result


def test_multiline_script_removal():
    """여러 줄에 걸친 script 태그가 제거되는지 확인."""
    html = """<html>
<head>
<script type="text/javascript">
    var x = 1;
    console.log(x);
</script>
</head>
<body><p>Content</p></body>
</html>"""
    result = _strip_html(html)
    assert "var x" not in result
    assert "console" not in result
    assert "Content" in result


def test_case_insensitive_tag_removal():
    """대소문자 혼합 태그도 제거되는지 확인."""
    html = "<SCRIPT>bad()</SCRIPT><STYLE>p{}</STYLE><P>Good</P>"
    result = _strip_html(html)
    assert "bad" not in result
    assert "p{}" not in result
    assert "Good" in result


def test_empty_input():
    """빈 문자열 입력 처리."""
    assert _strip_html("") == ""


def test_plain_text_passthrough():
    """HTML 태그 없는 텍스트는 그대로 유지."""
    text = "Just plain text with no HTML"
    assert _strip_html(text) == text
