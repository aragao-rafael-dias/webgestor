# WebSIG — Gestão do Transporte Escolar

> [!IMPORTANT]
> Projeto privado, em desenvolvimento e ainda não oficializado.
> O conteúdo deste repositório é destinado somente a testes e
> avaliação interna.

Sistema WebGIS desenvolvido para apoiar a gestão municipal do transporte escolar, reunindo em uma única aplicação o mapa de escolas e rotas, o acompanhamento de requisições, a organização dos setores responsáveis e o controle de acesso por perfil de usuário.

O projeto utiliza **Flask**, **PostgreSQL/PostGIS**, **Leaflet** e JavaScript modular. A estrutura foi pensada para uso por Secretarias Municipais de Educação e pode ser adaptada para diferentes municípios, bases cartográficas e fluxos administrativos.

> Projeto em desenvolvimento. Antes de utilizar em produção, revise as variáveis de ambiente, as permissões, a política de backups e a configuração HTTPS.

---

## Funcionalidades

- Visualização de escolas e rotas em mapa interativo.
- Filtro de rotas por região.
- Destaque de escolas com requisições pendentes.
- Cadastro e acompanhamento de requisições das escolas.
- Encaminhamento obrigatório da requisição ao setor responsável.
- Histórico de requisições filtrado conforme o perfil do usuário.
- Resposta e conclusão de requisições pelos setores autorizados.
- Cadastro de usuários com vínculo a uma ou várias escolas.
- Cadastro de usuários com vínculo a um ou vários setores.
- Definição de setor principal para usuários com múltiplos vínculos.
- Estrutura hierárquica de departamentos, coordenações, núcleos, assessorias e demais unidades administrativas.
- Painel contextual para escolas, setores e visão geral da rede.
- Área administrativa para gerenciamento de usuários.
- Exibição compacta de usuários com muitos vínculos.
- Geração de memorial de rota em PDF.
- Estrutura preparada para integração com sistemas externos, incluindo o SETE.

---

## Perfis e permissões

| Perfil | Acesso principal |
|---|---|
| `ADMIN` | Gerencia usuários e setores, visualiza toda a rede e todas as requisições. |
| `AUDITOR` | Consulta toda a rede e o histórico geral, sem responder requisições. |
| `DIRETOR` | Visualiza somente as escolas vinculadas, cria requisições e acompanha o histórico dessas escolas. |
| `SETOR` | Visualiza e responde somente às requisições encaminhadas aos seus setores ativos. |

As permissões são verificadas no backend. Ocultar um botão na interface não substitui a validação de acesso nas rotas da aplicação.

---

## Tecnologias

### Backend

- Python
- Flask
- Flask-Login
- Flask-WTF
- Flask-Migrate / Alembic
- SQLAlchemy
- GeoAlchemy2
- Argon2 para armazenamento seguro de senhas
- xhtml2pdf e Matplotlib para geração de memoriais

### Banco de dados

- PostgreSQL
- PostGIS
- Schema principal: `semed`
- Campos JSONB para informações complementares do WebSIG

### Frontend

- HTML5
- CSS3
- JavaScript com módulos ES
- Leaflet
- OpenStreetMap

---

## Estrutura principal

```text
webgestor/
├── comandos/
│   └── setores.py
├── migrations/
│   └── versions/
├── routes/
│   ├── admin.py
│   ├── auth.py
│   ├── escolas.py
│   ├── home.py
│   ├── memorial.py
│   ├── requisicoes.py
│   ├── rotas.py
│   └── setores.py
├── servicos/
│   └── setores.py
├── static/
│   ├── css/
│   │   └── style.css
│   └── js/
│       ├── admin.js
│       ├── api.js
│       ├── dashboard.js
│       ├── escolas.js
│       ├── mapa.js
│       ├── painel_contextual.js
│       ├── requisicoes.js
│       ├── state.js
│       └── templates/
├── templates/
│   ├── admin/
│   ├── index.html
│   ├── login.html
│   └── memorial.html
├── config.py
├── models.py
├── permissoes.py
├── requirements.txt
└── run.py
```

A estrutura pode variar conforme a versão do projeto. O arquivo `run.py` é o ponto de entrada atual da aplicação.

---

## Pré-requisitos

- Python 3.11 ou superior recomendado.
- PostgreSQL.
- Extensão PostGIS habilitada.
- Git.
- Ambiente virtual Python.

No PostgreSQL, prepare a extensão e o schema:

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE SCHEMA IF NOT EXISTS semed;
```

---

## Instalação

### 1. Clone o repositório

```bash
git clone <URL_DO_REPOSITORIO>
cd webgestor
```

### 2. Crie o ambiente virtual

#### Windows PowerShell

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

#### Linux ou macOS

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Instale as dependências

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

---

## Configuração do ambiente

Crie um arquivo `.env` na raiz do projeto:

```dotenv
SECRET_KEY=troque-por-uma-chave-longa-e-aleatoria

DB_USER=postgres
PASSWORD=sua_senha_do_postgresql
IP=localhost
PORT=5432
DB_NAME=SEMDU

APP_TIMEZONE=America/Maceio
FLASK_DEBUG=true
SESSION_COOKIE_SECURE=false
```

### Variáveis

| Variável | Descrição |
|---|---|
| `SECRET_KEY` | Chave usada pelo Flask para sessões e proteção CSRF. |
| `DB_USER` | Usuário do PostgreSQL. |
| `PASSWORD` | Senha do PostgreSQL. |
| `IP` | Endereço do servidor PostgreSQL. |
| `PORT` | Porta do PostgreSQL, normalmente `5432`. |
| `DB_NAME` | Nome do banco; o padrão do projeto é `SEMDU`. |
| `APP_TIMEZONE` | Fuso usado na apresentação de datas e horários. |
| `FLASK_DEBUG` | Ativa o modo de desenvolvimento. Não use `true` em produção. |
| `SESSION_COOKIE_SECURE` | Use `true` em produção quando o sistema estiver publicado com HTTPS. |

Nunca envie o arquivo `.env` ao GitHub. Mantenha-o no `.gitignore`.

---

## Banco de dados e migrações

A aplicação utiliza Flask-Migrate/Alembic.

### Aplicar as migrações existentes

```bash
python -m flask --app run:app db upgrade
```

### Criar uma nova migração após alterar os modelos

```bash
python -m flask --app run:app db migrate -m "descricao da alteracao"
```

Revise sempre o arquivo gerado em `migrations/versions/` antes de executar o upgrade, principalmente em tabelas espaciais.

```bash
python -m flask --app run:app db upgrade
```

### Consultar a revisão atual

```bash
python -m flask --app run:app db current
```

---

## Carga inicial dos setores

O projeto possui um comando CLI para cadastrar ou atualizar a estrutura administrativa inicial:

```bash
python -m flask --app run:app carregar-setores
```

O comando pode ser executado novamente para atualizar os registros já existentes sem duplicar a estrutura pelo nome.

---

## Criação do primeiro administrador

```bash
python -m flask --app run:app criar-admin
```

O terminal solicitará:

- nome completo;
- login;
- e-mail opcional;
- senha e confirmação.

As senhas devem possuir entre 12 e 128 caracteres e são armazenadas com Argon2.

---

## Executando o sistema

### Desenvolvimento

```bash
python -m flask --app run:app run --debug
```

Acesse:

```text
http://127.0.0.1:5000
```

Também é possível executar diretamente:

```bash
python run.py
```

### Conferir as rotas registradas

```bash
python -m flask --app run:app routes
```

---

## Fluxo de requisições

1. Um usuário com perfil `DIRETOR` acessa uma escola vinculada.
2. O diretor seleciona o setor responsável e descreve a necessidade.
3. A requisição é criada com status `Pendente`.
4. Usuários vinculados ao setor selecionado visualizam a solicitação.
5. Um usuário do setor registra a resposta.
6. O sistema grava o responsável, a data da resposta e altera o status para `Respondida`.
7. O diretor acompanha o retorno no histórico da escola.

Requisições antigas sem `setor_id` precisam ser classificadas antes de aparecerem para usuários de setor.

Exemplo de consulta:

```sql
SELECT
    id,
    escola_id,
    descricao,
    setor_id
FROM semed.requisicoes
WHERE setor_id IS NULL
ORDER BY id;
```

Exemplo de classificação:

```sql
UPDATE semed.requisicoes
SET setor_id = 4
WHERE id = 20;
```

---

## Principais endpoints

As rotas abaixo exigem autenticação, salvo configuração diferente no projeto.

| Método | Endpoint | Finalidade |
|---|---|---|
| `GET` | `/api/escolas` | Retorna as escolas em GeoJSON. |
| `GET` | `/api/rotas` | Retorna as rotas em GeoJSON. |
| `GET` | `/api/minhas-escolas` | Lista as escolas vinculadas ao diretor autenticado. |
| `GET` | `/api/setores` | Lista os setores ativos. |
| `GET` | `/api/meus-setores` | Lista os setores do usuário autenticado. |
| `GET` | `/api/escolas/<id>/requisicoes` | Retorna o histórico permitido para uma escola. |
| `POST` | `/api/requisicoes` | Cria uma nova requisição. |
| `POST` | `/api/requisicoes/<id>/responder` | Responde e conclui uma requisição. |
| `GET` | `/api/requisicoes/todas` | Retorna requisições filtradas conforme o perfil. |
| `GET` | `/api/requisicoes/alertas` | Retorna escolas com pendências visíveis ao usuário. |
| `GET` | `/api/rotas/<id>/memorial` | Gera o memorial da rota em PDF. |

Exemplo de criação de requisição:

```json
{
  "escola_id": 10,
  "setor_id": 4,
  "descricao": "Necessidade registrada pela unidade escolar"
}
```

---

## Modelos principais

- `Escola`: unidade escolar e sua geometria.
- `RotaGeral`: rota escolar e geometria linear.
- `Requisicao`: solicitação, setor responsável, status e resposta.
- `Usuario`: credenciais, perfil e situação da conta.
- `UsuarioEscola`: vínculo entre diretor e escola.
- `Setor`: unidade administrativa hierárquica.
- `UsuarioSetor`: vínculo entre usuário e setor, com indicação do vínculo principal.
- `EscolaPainel`: informações complementares enviadas pelo WebSIG para o painel contextual.

---

## Segurança

O projeto inclui:

- autenticação com Flask-Login;
- proteção global das páginas privadas;
- respostas JSON `401` para APIs sem autenticação;
- separação de permissões por perfil;
- validação dos vínculos no backend;
- hash de senhas com Argon2;
- proteção CSRF nos formulários Flask-WTF;
- cookies de sessão com `HttpOnly` e `SameSite=Lax`;
- opção de cookie seguro em ambientes HTTPS;
- normalização de login e e-mail;
- limite de tamanho para descrições e respostas.

Para produção:

- desative o modo debug;
- publique exclusivamente por HTTPS;
- configure `SESSION_COOKIE_SECURE=true`;
- use uma `SECRET_KEY` forte;
- mantenha backups automáticos do PostgreSQL;
- restrinja o acesso de rede ao banco;
- utilize um servidor WSGI adequado;
- registre logs e monitore erros da aplicação.

---

## Verificações úteis

### Validar os arquivos Python

```bash
python -m compileall routes servicos comandos models.py config.py run.py
```

### Conferir a situação das migrações

```bash
python -m flask --app run:app db current
python -m flask --app run:app db heads
```

### Consultar usuários e vínculos de setores

```sql
SELECT
    u.nome AS usuario,
    s.nome AS setor,
    us.principal,
    us.ativo,
    us.inicio_vinculo,
    us.fim_vinculo
FROM semed.usuarios_setores us
JOIN semed.usuarios u
    ON u.id = us.usuario_id
JOIN semed.setores s
    ON s.id = us.setor_id
ORDER BY
    u.nome,
    us.principal DESC,
    s.nome;
```

---

## Implantação em outro município

A aplicação pode ser adaptada para outras Secretarias de Educação. Os principais pontos de configuração são:

- banco de escolas;
- geometrias das escolas e rotas;
- regiões ou zonas de transporte;
- organograma e setores responsáveis;
- identidade visual;
- campos exibidos no painel contextual;
- regras administrativas locais;
- integração com o SETE ou outros sistemas institucionais.

Ao importar dados espaciais, confira o sistema de referência e normalize a saída usada no mapa para `EPSG:4326`.

---

## Roadmap

- Edição e inativação de usuários pela interface administrativa.
- Administração visual completa dos setores.
- Auditoria detalhada de alterações.
- Anexos em requisições.
- Notificações por e-mail ou mensageria institucional.
- Relatórios e indicadores de tempo de atendimento.
- Integração ampliada com o SETE.
- Testes automatizados de permissões e APIs.
- Implantação com Docker e pipeline de integração contínua.

---

## Contribuição

1. Crie uma branch a partir da versão principal.
2. Faça alterações pequenas e objetivas.
3. Não inclua credenciais, arquivos `.env` ou dados pessoais.
4. Revise as migrações antes de enviá-las.
5. Teste os quatro perfis de usuário.
6. Abra um pull request descrevendo o problema e a solução.

Exemplo:

```bash
git checkout -b feature/nome-da-melhoria
git add .
git commit -m "feat: descreve a melhoria"
git push origin feature/nome-da-melhoria
```

---

## Dados sensíveis

Não publique no repositório:

- senhas ou hashes exportados;
- arquivo `.env`;
- backups do banco;
- dados pessoais de estudantes;
- documentos internos;
- chaves de API;
- arquivos com informações protegidas ou restritas.

Use dados fictícios ou anonimizados em demonstrações públicas.

---

## Situação do projeto

Este projeto encontra-se em fase de desenvolvimento, testes e
avaliação técnica.

O repositório é privado e seu conteúdo não representa, neste momento,
uma versão oficial, homologada ou publicada pela Administração Pública.

A definição da titularidade, da forma de distribuição e da eventual
licença de uso do software dependerá de formalização e autorização
institucional.

## Uso restrito

O código-fonte, a documentação, os dados, os modelos e os demais
arquivos deste repositório são destinados exclusivamente ao
desenvolvimento e à avaliação interna do projeto.

O acesso ao repositório não concede autorização para:

- publicar ou redistribuir o código;
- compartilhar o conteúdo com terceiros;
- utilizar o sistema comercialmente;
- criar ou distribuir versões derivadas;
- divulgar dados, credenciais ou informações internas do projeto.

Todos os direitos permanecem reservados aos respectivos titulares,
cuja definição será formalizada oportunamente.

## Licença

Este projeto ainda não possui licença pública de uso ou distribuição.

Nenhuma licença de software livre ou de código aberto é concedida
nesta etapa.