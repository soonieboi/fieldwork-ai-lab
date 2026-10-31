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
    generated = sub.add_parser('generate', help='Opt-in endpoint response; citations do not establish truth')
    generated.add_argument('question')
    generated.add_argument('--corpus',choices=('shop','lab'),default='shop')
    bounded=sub.add_parser('agent-run',help='Bounded structured-choice agent; offline walkthrough by default')
    bounded.add_argument('question')
    bounded.add_argument('--mode',choices=('offline','endpoint'),default='offline')
    bounded.add_argument('--corpus',choices=('shop','lab'),default='shop')
    bounded.add_argument('--max-steps',type=int,default=6)
    bounded.add_argument('--seconds',type=float,default=15)
    bounded.add_argument('--output-budget',type=int,default=1536)
    agent = sub.add_parser('agent')
    agent.add_argument('--task', choices=['retrieval', 'safety', 'serving'], default='retrieval')
    agent.add_argument('--budget', type=int, default=6)
    sub.add_parser('evaluate')
    suite = sub.add_parser('eval-suite', help='Versioned documentation QA; separate split reports')
    suite.add_argument('--split', choices=('development','heldout'), required=True)
    suite.add_argument('--output', required=True)
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
        elif args.command == 'generate':
            from .generation import GenerationError, generate
            from .core import ROOT
            try:
                result=generate(Index(ROOT/'examples/shop') if args.corpus=='shop' else Index(),args.question)
            except GenerationError as exc:
                print(json.dumps({'error':str(exc),'error_code':exc.code}))
                raise SystemExit(1)
        elif args.command == 'agent':
            result = run_agent(Index(), args.task, args.budget)
        elif args.command == 'agent-run':
            from .core import ROOT
            from .generation import GenerationConfig
            from .model_agent import AgentBudget,AgentError,agent_config,offline_choice,run_model_agent
            try:
                config=agent_config() if args.mode=='endpoint' else GenerationConfig('http://127.0.0.1/unused','offline-scripted-not-a-model',max_tokens=128)
                if config is None:raise AgentError('disabled')
                result=run_model_agent(Index(ROOT/'examples/shop') if args.corpus=='shop' else Index(),args.question,config,
                    AgentBudget(args.max_steps,args.seconds,args.output_budget),
                    provider=offline_choice if args.mode=='offline' else None,
                    mode='offline_scripted' if args.mode=='offline' else 'configured_endpoint')
            except AgentError as exc:
                print(json.dumps({'error':str(exc),'error_code':exc.code}));raise SystemExit(1)
        elif args.command == 'evaluate':
            result = evaluate(Index())
        elif args.command == 'eval-suite':
            from .abstention import load_policy
            from .evaluation import run_suite, write_json
            report = run_suite(args.split, load_policy())
            write_json(args.output, report)
            result = {b: r['summary'] for b,r in report['baselines'].items()}
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
