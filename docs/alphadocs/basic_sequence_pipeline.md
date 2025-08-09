<!-- Path: docs/alphadocs/basic_sequence_pipeline.md -->
간단한 시퀀스 생성 → 평균 계산 → 스케일 조정을 수행하는 파이프라인 설계.

1. `sequence_generator_node`가 기본 수열을 생성합니다.
2. `average_indicator_node`가 수열의 평균을 계산합니다.
3. `scale_transform_node`가 평균값을 상수 배로 스케일합니다.
