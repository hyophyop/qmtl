# type: ignore
import argparse
import re
from datetime import datetime
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None  # type: ignore


class AlphaDocsManager:
    """AlphaDocs 문서 관리 클래스"""

    def __init__(self, docs_dir=None):
        self.docs_dir = docs_dir or Path(__file__).parent / "alphadocs"
        self.registry_file = self.docs_dir.parent / "alphadocs_registry.yml"

    def load_registry(self):
        """레지스트리 파일을 로드합니다."""
        if not self.registry_file.exists() or yaml is None:
            return []

        with open(self.registry_file, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or []

    def save_registry(self, registry):
        """레지스트리를 파일에 저장합니다."""
        if yaml is None:
            return

        with open(self.registry_file, 'w', encoding='utf-8') as f:
            yaml.dump(registry, f, default_flow_style=False, sort_keys=False,
                     allow_unicode=True)

    def create_new_doc(self, title, author="Unknown", priority="normal", tags=None):
        """새로운 AlphaDocs 문서를 생성합니다."""
        tags = tags or []

        # 파일명 생성 (제목을 기반으로)
        filename = re.sub(r'[^\w\s-]', '', title.lower())
        filename = re.sub(r'[\s_]+', '-', filename)
        filename = f"{filename}.md"

        doc_path = self.docs_dir / filename

        # 기본 템플릿 내용
        content = f"""# {title}

## 문서 정보
- **저자**: {author}
- **생성일**: {datetime.now().strftime('%Y-%m-%d')}
- **버전**: v1.0.0
- **상태**: draft
- **우선순위**: {priority}
- **태그**: {', '.join(tags)}

## 개요
[아이디어 또는 전략의 간단한 개요]

## 배경
[아이디어가 나온 배경과 맥락]

## QMTL Integration
- **Transform 이름**: [예상되는 transform 이름]
- **필요한 노드들**: [필요한 generator, indicator, transform 노드들]
- **테스트 범위**: [어떤 시나리오로 테스트할 것인지]
"""

        # 파일 생성
        doc_path.write_text(content, encoding='utf-8')

        # 레지스트리에 추가
        registry = self.load_registry()
        new_entry = {{
            "doc": f"docs/alphadocs/{filename}",
            "status": "draft",
            "modules": [],
            "priority": priority,
            "tags": tags,
            "created": datetime.now().isoformat(),
            "version": "v1.0.0"
        }}
        registry.append(new_entry)
        self.save_registry(registry)

        print(f"✅ 새로운 AlphaDocs 문서가 생성되었습니다: {{doc_path}}")
        return doc_path

    def generate_review_report(self):
        """검토 리포트를 생성합니다."""
        registry = self.load_registry()

        report_lines = [
            "# AlphaDocs 검토 리포트",
            f"생성일: {{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}}",
            "",
            "## 상태별 문서 수",
        ]

        status_counts = {{}}
        for doc in registry:
            status = doc.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1

        for status, count in status_counts.items():
            report_lines.append(f"- {{status}}: {{count}}개")

        report_lines.extend([
            "",
            "## 우선순위별 문서",
            "### High Priority"
        ])

        high_priority = [doc for doc in registry if doc.get("priority") == "high"]
        for doc in high_priority:
            report_lines.append(f"- {{doc['doc']}} ({{doc.get('status', 'unknown')}})")

        return "\n".join(report_lines)


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description="AlphaDocs 관리 도구")
    subparsers = parser.add_subparsers(dest="command", help="사용 가능한 명령어")

    # 새 문서 생성
    create_parser = subparsers.add_parser("create", help="새로운 AlphaDocs 문서 생성")
    create_parser.add_argument("title", help="문서 제목")
    create_parser.add_argument("--author", default="Unknown", help="저자 이름")
    create_parser.add_argument("--priority", default="normal",
                              choices=["low", "normal", "high", "critical"],
                              help="우선순위")
    create_parser.add_argument("--tags", nargs="*", help="태그들")

    # 검토 리포트 생성
    subparsers.add_parser("review", help="검토 리포트 생성")

    args = parser.parse_args()

    manager = AlphaDocsManager()

    if args.command == "create":
        manager.create_new_doc(args.title, args.author, args.priority, args.tags)
    elif args.command == "review":
        report = manager.generate_review_report()
        print(report)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
