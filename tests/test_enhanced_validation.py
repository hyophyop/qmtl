"""Tests for enhanced error handling and input validation."""

import pytest
from qmtl.sdk import (
    SourceNode, 
    ProcessingNode, 
    TagQueryNode,
    StreamInput,
    MatchMode,
    QMTLValidationError,
    NodeValidationError,
    InvalidParameterError,
    InvalidTagError,
    InvalidIntervalError,
    InvalidPeriodError,
    InvalidNameError,
    validate_tag,
    validate_name,
)


class TestNameValidation:
    """Test name parameter validation."""
    
    def test_valid_names(self):
        """Test that valid names are accepted."""
        assert validate_name("test_node") == "test_node"
        assert validate_name("TestNode123") == "TestNode123"
        assert validate_name("node with spaces") == "node with spaces"
        assert validate_name(None) is None
        
    def test_empty_name_raises_error(self):
        """Test that empty names raise InvalidNameError."""
        with pytest.raises(InvalidNameError, match="must not be empty"):
            validate_name("")
        with pytest.raises(InvalidNameError, match="must not be empty"):
            validate_name("   ")
    
    def test_invalid_name_type_raises_error(self):
        """Test that non-string names raise InvalidNameError."""
        with pytest.raises(InvalidNameError, match="must be a string"):
            validate_name(123)
    
    def test_long_name_raises_error(self):
        """Test that overly long names raise InvalidNameError."""
        long_name = "a" * 201
        with pytest.raises(InvalidNameError, match="must not exceed 200 characters"):
            validate_name(long_name)
    
    def test_node_with_invalid_name(self):
        """Test that Node constructor validates names."""
        with pytest.raises(InvalidNameError):
            SourceNode(name="", interval="1s", period=1)


class TestTagValidation:
    """Test tag parameter validation."""
    
    def test_valid_tags(self):
        """Test that valid tags are accepted."""
        assert validate_tag("valid_tag") == "valid_tag"
        assert validate_tag("tag-123") == "tag-123"
        assert validate_tag("tag.with.dots") == "tag.with.dots"
        assert validate_tag("TAG_123") == "TAG_123"
    
    def test_empty_tag_raises_error(self):
        """Test that empty tags raise InvalidTagError."""
        with pytest.raises(InvalidTagError, match="must not be empty"):
            validate_tag("")
        with pytest.raises(InvalidTagError, match="must not be empty"):
            validate_tag("   ")
    
    def test_invalid_tag_type_raises_error(self):
        """Test that non-string tags raise InvalidTagError."""
        with pytest.raises(InvalidTagError, match="must be a string"):
            validate_tag(123)
    
    def test_invalid_tag_characters_raise_error(self):
        """Test that tags with invalid characters raise InvalidTagError."""
        with pytest.raises(InvalidTagError, match="must contain only"):
            validate_tag("tag with spaces")
        with pytest.raises(InvalidTagError, match="must contain only"):
            validate_tag("tag@invalid")
        with pytest.raises(InvalidTagError, match="must contain only"):
            validate_tag("tag/invalid")
    
    def test_long_tag_raises_error(self):
        """Test that overly long tags raise InvalidTagError."""
        long_tag = "a" * 101
        with pytest.raises(InvalidTagError, match="must not exceed 100 characters"):
            validate_tag(long_tag)
    
    def test_node_with_invalid_tags(self):
        """Test that Node constructor validates tags."""
        with pytest.raises(InvalidTagError):
            SourceNode(tags=["valid", ""], interval="1s", period=1)
    
    def test_node_with_duplicate_tags(self):
        """Test that Node constructor rejects duplicate tags."""
        with pytest.raises(InvalidParameterError, match="duplicate tag"):
            SourceNode(tags=["tag1", "tag2", "tag1"], interval="1s", period=1)
    
    def test_add_tag_validation(self):
        """Test that add_tag method validates tags."""
        node = SourceNode(interval="1s", period=1)
        with pytest.raises(InvalidTagError):
            node.add_tag("")
        
        # Test that valid tags are added
        node.add_tag("valid_tag")
        assert "valid_tag" in node.tags
        
        # Test that duplicate tags are not added again
        node.add_tag("valid_tag")
        assert node.tags.count("valid_tag") == 1


class TestParameterValidation:
    """Test general parameter validation."""
    
    def test_invalid_tags_parameter_type(self):
        """Test that non-list tags parameter raises error."""
        with pytest.raises(InvalidParameterError, match="tags must be a list"):
            SourceNode(tags="not_a_list", interval="1s", period=1)
    
    def test_invalid_config_parameter_type(self):
        """Test that non-dict config parameter raises error."""
        with pytest.raises(InvalidParameterError, match="config must be a dictionary"):
            SourceNode(config="not_a_dict", interval="1s", period=1)
    
    def test_invalid_schema_parameter_type(self):
        """Test that non-dict schema parameter raises error."""
        with pytest.raises(InvalidParameterError, match="schema must be a dictionary"):
            SourceNode(schema="not_a_dict", interval="1s", period=1)
    
    def test_valid_config_and_schema(self):
        """Test that valid config and schema are accepted."""
        node = SourceNode(
            config={"key": "value"}, 
            schema={"type": "object"}, 
            interval="1s", 
            period=1
        )
        assert node.config == {"key": "value"}
        assert node.schema == {"type": "object"}


class TestIntervalValidation:
    """Test enhanced interval validation."""
    
    def test_interval_upper_bound(self):
        """Test that intervals exceeding 24 hours are rejected."""
        with pytest.raises(InvalidIntervalError, match="must not exceed 24 hours"):
            SourceNode(interval=86401, period=1)  # 1 second over 24 hours
        
        with pytest.raises(InvalidIntervalError, match="must not exceed 24 hours"):
            SourceNode(interval="25h", period=1)
    
    def test_valid_interval_bounds(self):
        """Test that valid intervals are accepted."""
        node = SourceNode(interval=86400, period=1)  # exactly 24 hours
        assert node.interval == 86400
        
        node = SourceNode(interval="24h", period=1)
        assert node.interval == 86400


class TestPeriodValidation:
    """Test enhanced period validation."""
    
    def test_period_upper_bound(self):
        """Test that periods exceeding 10000 are rejected."""
        with pytest.raises(InvalidPeriodError, match="must not exceed 10000"):
            SourceNode(interval="1s", period=10001)
    
    def test_valid_period_bounds(self):
        """Test that valid periods are accepted."""
        node = SourceNode(interval="1s", period=10000)  # exactly at limit
        assert node.period == 10000


class TestFeedMethodValidation:
    """Test feed method parameter validation."""
    
    def test_invalid_upstream_id(self):
        """Test that invalid upstream_id parameters raise errors."""
        node = SourceNode(interval="1s", period=1)
        
        with pytest.raises(InvalidParameterError, match="upstream_id must be a string"):
            node.feed(123, 60, 1234567890, {})
        
        with pytest.raises(InvalidParameterError, match="upstream_id must not be empty"):
            node.feed("", 60, 1234567890, {})
        
        with pytest.raises(InvalidParameterError, match="upstream_id must not be empty"):
            node.feed("   ", 60, 1234567890, {})
    
    def test_invalid_interval_parameter(self):
        """Test that invalid interval parameters raise errors."""
        node = SourceNode(interval="1s", period=1)
        
        with pytest.raises(InvalidParameterError, match="interval must be an integer"):
            node.feed("upstream", "60", 1234567890, {})
        
        with pytest.raises(InvalidParameterError, match="interval must be positive"):
            node.feed("upstream", 0, 1234567890, {})
        
        with pytest.raises(InvalidParameterError, match="interval must be positive"):
            node.feed("upstream", -60, 1234567890, {})
    
    def test_invalid_timestamp_parameter(self):
        """Test that invalid timestamp parameters raise errors."""
        node = SourceNode(interval="1s", period=1)
        
        with pytest.raises(InvalidParameterError, match="timestamp must be an integer"):
            node.feed("upstream", 60, "1234567890", {})
        
        with pytest.raises(InvalidParameterError, match="timestamp must not be negative"):
            node.feed("upstream", 60, -1, {})
    
    def test_invalid_on_missing_parameter(self):
        """Test that invalid on_missing parameters raise errors."""
        node = SourceNode(interval="1s", period=1)
        
        with pytest.raises(InvalidParameterError, match="on_missing must be 'skip' or 'fail'"):
            node.feed("upstream", 60, 1234567890, {}, on_missing="invalid")
    
    def test_valid_feed_parameters(self):
        """Test that valid feed parameters are accepted."""
        node = SourceNode(interval="1s", period=1)
        
        # Should not raise any exceptions
        result = node.feed("upstream", 60, 1234567890, {"data": "test"})
        assert isinstance(result, bool)
        
        # Test with on_missing="skip" (default) - should not raise RuntimeError
        result = node.feed("upstream", 60, 1234567891, {"data": "test"}, on_missing="skip")
        assert isinstance(result, bool)


class TestTagQueryNodeValidation:
    """Test TagQueryNode-specific validation."""
    
    def test_invalid_query_tags_type(self):
        """Test that non-list query_tags raise error."""
        with pytest.raises(InvalidParameterError, match="query_tags must be a list"):
            TagQueryNode("not_a_list", interval="1s", period=1)
    
    def test_empty_query_tags(self):
        """Test that empty query_tags raise error."""
        with pytest.raises(InvalidParameterError, match="query_tags must not be empty"):
            TagQueryNode([], interval="1s", period=1)
    
    def test_duplicate_query_tags(self):
        """Test that duplicate query_tags raise error."""
        with pytest.raises(InvalidParameterError, match="duplicate query tag"):
            TagQueryNode(["tag1", "tag2", "tag1"], interval="1s", period=1)
    
    def test_invalid_query_tag_format(self):
        """Test that invalid tag formats in query_tags raise error."""
        with pytest.raises(InvalidTagError):
            TagQueryNode(["valid_tag", ""], interval="1s", period=1)
    
    def test_valid_query_tags(self):
        """Test that valid query_tags are accepted."""
        node = TagQueryNode(["tag1", "tag2"], interval="1s", period=1)
        assert node.query_tags == ["tag1", "tag2"]
        assert node.tags == ["tag1", "tag2"]


class TestExceptionHierarchy:
    """Test that exception hierarchy works correctly."""
    
    def test_exception_inheritance(self):
        """Test that custom exceptions inherit correctly."""
        assert issubclass(QMTLValidationError, ValueError)
        assert issubclass(NodeValidationError, QMTLValidationError)
        assert issubclass(InvalidParameterError, NodeValidationError)
        assert issubclass(InvalidTagError, NodeValidationError)
        assert issubclass(InvalidIntervalError, NodeValidationError)
        assert issubclass(InvalidPeriodError, NodeValidationError)
        assert issubclass(InvalidNameError, NodeValidationError)
    
    def test_catching_base_exception(self):
        """Test that base exceptions can catch specific errors."""
        with pytest.raises(QMTLValidationError):
            validate_tag("")
        
        with pytest.raises(NodeValidationError):
            validate_name("")