import pytest

from qmtl.services.dagmanager.controlbus_producer import ControlBusProducer


@pytest.mark.asyncio
async def test_start_warns_when_optional_controlbus_missing(caplog):
    producer = ControlBusProducer(brokers=[], required=False)

    with caplog.at_level("WARNING"):
        await producer.start()

    assert "ControlBus disabled" in caplog.text


@pytest.mark.asyncio
async def test_start_raises_when_controlbus_required_and_missing():
    producer = ControlBusProducer(brokers=[], required=True)

    with pytest.raises(RuntimeError, match="ControlBus unavailable"):
        await producer.start()
