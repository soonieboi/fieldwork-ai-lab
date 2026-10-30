import argparse
import json
import os
from .core import Index, benchmark, evaluate, replay, run_agent


def main():
    parser = argparse.ArgumentParser(description='Local AI engineering lab')
    sub = parser.add_subparsers(dest='command', required=True)
    serve = sub.add_parser('serve')
    serve.add_argument('--port', type=int, default=8080)
    ask = sub.add_parser('ask')
    ask.add_argument('question')
    agent = sub.add_parser('agent')
    agent.add_argument('--task', choices=['retrieval', 'safety', 'serving'], default='retrieval')
    agent.add_argument('--budget', type=int, default=6)
    sub.add_parser('evaluate')
    sub.add_parser('replay')
    bench = sub.add_parser('benchmark')
    bench.add_argument('--base-url', required=True, help='OpenAI-compatible API root including /v1')
    bench.add_argument('--model', required=True)
    bench.add_argument('--runs', type=int, default=3)
    bench.add_argument('--timeout', type=int, default=30)
    args = parser.parse_args()
    try:
        if args.command == 'serve':
            from .server import serve
            serve(args.port)
            return
        if args.command == 'ask':
            result = Index().answer(args.question)
        elif args.command == 'agent':
            result = run_agent(Index(), args.task, args.budget)
        elif args.command == 'evaluate':
            result = evaluate(Index())
        elif args.command == 'replay':
            result = replay()
        else:
            result = benchmark(args.base_url, args.model, os.environ.get('LAB_API_KEY', ''), args.runs, args.timeout)
        print(json.dumps(result, indent=2))
        if args.command == 'benchmark' and result['failures']:
            raise SystemExit(1)
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
