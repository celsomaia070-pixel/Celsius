#!/usr/bin/env python3
"""Gerador de chaves de licença do Celsius.

Uso:
    python tools/generate_license.py --customer "Nome" --email "email@ex.com" --days 365
    python tools/generate_license.py --customer "Nome" --email "email@ex.com" --expiry 2027-12-31
    python tools/generate_license.py --generate-keypair
    python tools/generate_license.py --list-trials
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.license import (
    _get_data_dir,
    create_license_key,
    generate_key_pair,
    serialize_private_key,
    serialize_public_key,
)


def cmd_generate_keypair(args):
    private_key, public_key = generate_key_pair()
    priv_pem = serialize_private_key(private_key)
    pub_pem = serialize_public_key(public_key)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    priv_path = output_dir / "private_key.pem"
    pub_path = output_dir / "public_key.pem"

    priv_path.write_text(priv_pem, encoding="utf-8")
    pub_path.write_text(pub_pem, encoding="utf-8")

    priv_path.chmod(0o600)

    print(f"Par de chaves gerado em: {output_dir}")
    print(f"  Chave privada: {priv_path}")
    print(f"  Chave publica:  {pub_path}")
    print()
    print("IMPORTANTE: Guarde a chave privada em local seguro!")
    print("A chave privada NUNCA deve ser distribuida.")
    print()
    print("Para usar a chave publica personalizada, substitua o _EMBEDDED_PUBLIC_KEY_PEM")
    print("em core/license.py pelo conteudo de public_key.pem")


def cmd_generate_license(args):
    private_key_pem = Path(args.private_key).read_bytes()

    if args.expiry:
        expiry_date = datetime.fromisoformat(args.expiry)
    elif args.days:
        expiry_date = datetime.now() + timedelta(days=args.days)
    else:
        expiry_date = datetime.now() + timedelta(days=365)

    hwid = args.hwid if args.hwid else None

    key = create_license_key(
        customer=args.customer,
        email=args.email,
        expiry_date=expiry_date,
        private_key_pem=private_key_pem,
        hwid=hwid,
    )

    print("=" * 70)
    print("CHAVE DE LICENCA GERADA")
    print("=" * 70)
    print()
    print(f"Cliente:    {args.customer}")
    print(f"Email:      {args.email}")
    print(f"Expira em:  {expiry_date.strftime('%d/%m/%Y %H:%M')}")
    print(f"HWID:       {hwid or '(qualquer computador)'}")
    print()
    print("-" * 70)
    print("CHAVE:")
    print("-" * 70)
    print(key)
    print("-" * 70)
    print()

    if args.save:
        save_path = Path(args.save)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        licenses = []
        if save_path.exists():
            try:
                licenses = json.loads(save_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                licenses = []
        licenses.append(
            {
                "customer": args.customer,
                "email": args.email,
                "expiry": expiry_date.isoformat(),
                "hwid": hwid,
                "key": key,
                "created": datetime.now().isoformat(),
            }
        )
        save_path.write_text(json.dumps(licenses, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Licença salva em: {save_path}")


def cmd_list_trials(args):
    data_dir = _get_data_dir()
    trial_file = data_dir / ".trial"

    print("=== Status de Trials ===")
    print(f"Diretorio de dados: {data_dir}")
    print()

    if trial_file.exists():
        from datetime import datetime

        first_run = datetime.fromisoformat(trial_file.read_text(encoding="utf-8").strip())
        from core.license import TRIAL_DAYS, get_trial_info

        info = get_trial_info()
        print(f"Primeiro uso:  {first_run.strftime('%d/%m/%Y %H:%M')}")
        print(f"Dias de trial: {TRIAL_DAYS}")
        print(f"Dias restantes: {info['days_remaining']}")
        print(f"Expirado:      {'Sim' if info['expired'] else 'Nao'}")
    else:
        print("Nenhum trial registrado.")

    license_file = data_dir / ".license"
    print()
    if license_file.exists():
        from core.license import validate_license_key

        key_str = license_file.read_text(encoding="utf-8").strip()
        valid, message, payload = validate_license_key(key_str)
        print(f"Status da licenca: {'VALIDA' if valid else 'INVALIDA'}")
        print(f"Mensagem: {message}")
        if payload:
            print(f"Cliente:  {payload.get('customer', '')}")
            print(f"Email:    {payload.get('email', '')}")
            print(f"Expira:   {payload.get('expiry', '')}")
    else:
        print("Nenhuma licença instalada.")


def main():
    parser = argparse.ArgumentParser(
        description="Gerador de chaves de licenca do Celsius",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Comando a executar")

    kp = subparsers.add_parser("keypair", help="Gerar par de chaves RSA")
    kp.add_argument("--output", default="keys", help="Diretorio de saida (default: keys)")

    lic = subparsers.add_parser("license", help="Gerar chave de licenca")
    lic.add_argument("--customer", required=True, help="Nome do cliente")
    lic.add_argument("--email", required=True, help="Email do cliente")
    lic.add_argument("--days", type=int, help="Dias ate expirar")
    lic.add_argument("--expiry", help="Data de expiracao (YYYY-MM-DD)")
    lic.add_argument("--hwid", help="Hardware ID para vincular")
    lic.add_argument(
        "--private-key",
        required=True,
        help="Caminho para a chave privada PEM, mantida fora do projeto",
    )
    lic.add_argument("--save", help="Salvar em arquivo JSON")

    subparsers.add_parser("trials", help="Listar trials e licencas")

    args = parser.parse_args()
    if args.command == "keypair":
        cmd_generate_keypair(args)
    elif args.command == "license":
        cmd_generate_license(args)
    elif args.command == "trials":
        cmd_list_trials(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
