# --- Federacao GitHub Actions -> AWS (sem credenciais de longa duracao) ---------
resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

# Boundary dos roles das Lambdas: sem iam:*, sem kms:* amplo.
data "aws_iam_policy_document" "boundary" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:FilterLogEvents"]
    resources = ["arn:aws:logs:${local.cfg.regiao}:${local.conta}:log-group:/aws/lambda/${local.prefixo}-*:*", "arn:aws:logs:${local.cfg.regiao}:${local.conta}:log-group:/revenda/${local.cfg.ambiente}/*:*"]
  }
  statement {
    sid = "EntregaDeLogsDaSaga"
    actions = [
      "logs:CreateLogDelivery", "logs:GetLogDelivery", "logs:UpdateLogDelivery", "logs:DeleteLogDelivery",
      "logs:ListLogDeliveries", "logs:PutResourcePolicy", "logs:DescribeResourcePolicies", "logs:DescribeLogGroups",
    ]
    resources = ["*"]
  }
  statement {
    sid       = "ObservabilidadeEMetricas"
    actions   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords", "cloudwatch:PutMetricData"]
    resources = ["*"]
  }
  statement {
    sid       = "Parametros"
    actions   = ["ssm:GetParameter", "ssm:GetParameters", "ssm:PutParameter", "ssm:DeleteParameter"]
    resources = ["arn:aws:ssm:${local.cfg.regiao}:${local.conta}:parameter/revenda/${local.cfg.ambiente}/*"]
  }
  statement {
    sid       = "ChavesGerenciadasViaServico"
    actions   = ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${local.cfg.regiao}.amazonaws.com", "dynamodb.${local.cfg.regiao}.amazonaws.com", "sqs.${local.cfg.regiao}.amazonaws.com", "sns.${local.cfg.regiao}.amazonaws.com"]
    }
  }
  statement {
    sid = "ServicosDaAplicacao"
    actions = [
      "dynamodb:*Item", "dynamodb:Query", "dynamodb:Scan", "dynamodb:DescribeStream", "dynamodb:GetRecords",
      "dynamodb:GetShardIterator", "dynamodb:ListStreams",
      "cognito-idp:Admin*", "cognito-idp:List*", "cognito-idp:DescribeUserPool",
      "sns:Publish", "sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes",
      "states:StartExecution", "states:SendTask*", "states:ListExecutions", "states:RedriveExecution", "states:DescribeExecution",
      "lambda:InvokeFunction", "execute-api:Invoke",
    ]
    resources = ["*"]
  }
}

# Isolamento da chave privada PII: negada a qualquer role de funcao, exceto clientes-interno e lgpd-worker.
data "aws_iam_policy_document" "boundary_completa" {
  source_policy_documents = [data.aws_iam_policy_document.boundary.json]

  statement {
    sid       = "NegarChavePrivadaPii"
    effect    = "Deny"
    actions   = ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"]
    resources = ["arn:aws:ssm:${local.cfg.regiao}:${local.conta}:parameter/revenda/${local.cfg.ambiente}/segredos/pii-chave-privada-*"]
    condition {
      test     = "ArnNotLike"
      variable = "aws:PrincipalArn"
      values = [
        "arn:aws:iam::${local.conta}:role/${local.prefixo}-fn-clientes-interno",
        "arn:aws:iam::${local.conta}:role/${local.prefixo}-fn-lgpd-worker",
      ]
    }
  }
}

resource "aws_iam_policy" "boundary" {
  name   = local.boundary_nm
  policy = data.aws_iam_policy_document.boundary_completa.json
}

# Role de deploy: assumida so a partir da main.
data "aws_iam_policy_document" "confianca_deploy" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values = concat(
        [for r in local.repo_oidc_subs : "${r}:ref:refs/heads/main"],
        # Job de destroy roda no environment `dev` (com revisor) so no modo de controles avancados.
        var.github_controles_avancados ? [for r in local.repo_oidc_subs : "${r}:environment:dev"] : [],
      )
    }
  }
}

resource "aws_iam_role" "deploy" {
  name                 = "gha-deploy-${local.cfg.ambiente}"
  assume_role_policy   = data.aws_iam_policy_document.confianca_deploy.json
  max_session_duration = 3600
}

# ARNs do projeto reaproveitados nas policies de deploy e de plano.
locals {
  regiao = local.cfg.regiao
  arns = {
    lambda = [
      "arn:aws:lambda:${local.regiao}:${local.conta}:function:${local.prefixo}-*",
      "arn:aws:lambda:${local.regiao}:${local.conta}:function:${local.prefixo}-*:*",
      "arn:aws:lambda:${local.regiao}:${local.conta}:layer:${local.prefixo}-*",
      "arn:aws:lambda:${local.regiao}:${local.conta}:layer:${local.prefixo}-*:*",
      "arn:aws:lambda:${local.regiao}:${local.conta}:event-source-mapping:*",
    ]
    dynamodb = [
      "arn:aws:dynamodb:${local.regiao}:${local.conta}:table/${local.prefixo}-*",
      "arn:aws:dynamodb:${local.regiao}:${local.conta}:table/${local.prefixo}-*/index/*",
      "arn:aws:dynamodb:${local.regiao}:${local.conta}:table/${local.prefixo}-*/stream/*",
    ]
    apigateway = [
      "arn:aws:apigateway:${local.regiao}::/restapis",
      "arn:aws:apigateway:${local.regiao}::/restapis/*",
      "arn:aws:apigateway:${local.regiao}::/tags/*",
    ]
    cognito = ["arn:aws:cognito-idp:${local.regiao}:${local.conta}:userpool/*"]
    mensageria = [
      "arn:aws:sns:${local.regiao}:${local.conta}:${local.prefixo}-*",
      "arn:aws:sqs:${local.regiao}:${local.conta}:${local.prefixo}-*",
    ]
    orquestracao = [
      "arn:aws:states:${local.regiao}:${local.conta}:stateMachine:${local.prefixo}-*",
      "arn:aws:states:${local.regiao}:${local.conta}:execution:${local.prefixo}-*/*",
      "arn:aws:scheduler:${local.regiao}:${local.conta}:schedule/default/${local.prefixo}-*",
      "arn:aws:scheduler:${local.regiao}:${local.conta}:schedule-group/default",
    ]
    # As APIs de tag usam o ARN do grupo sem o sufixo ":*"; as demais, com ele.
    logs = flatten([
      for g in ["/aws/lambda/${local.prefixo}-*", "/revenda/${local.cfg.ambiente}/*", "/aws/vendedlogs/states/${local.prefixo}-*"] :
      ["arn:aws:logs:${local.regiao}:${local.conta}:log-group:${g}", "arn:aws:logs:${local.regiao}:${local.conta}:log-group:${g}:*"]
    ])
    # A raiz do caminho tambem entra: GetParametersByPath usa o ARN sem o "/*".
    ssm = ["arn:aws:ssm:${local.regiao}:${local.conta}:parameter/revenda/${local.cfg.ambiente}", "arn:aws:ssm:${local.regiao}:${local.conta}:parameter/revenda/${local.cfg.ambiente}/*"]
    cloudwatch = [
      "arn:aws:cloudwatch:${local.regiao}:${local.conta}:alarm:${local.prefixo}-*",
      "arn:aws:cloudwatch::${local.conta}:dashboard/${local.prefixo}*",
    ]
    xray        = ["arn:aws:xray:${local.regiao}:${local.conta}:sampling-rule/*"]
    site_bucket = ["arn:aws:s3:::${local.prefixo}-web-*", "arn:aws:s3:::${local.prefixo}-web-*/*"]
    roles       = ["arn:aws:iam::${local.conta}:role/${local.prefixo}-*"]
  }
}

# Servicos de aplicacao: acoes liberadas por servico (curingas), escopo restrito aos recursos do projeto.
data "aws_iam_policy_document" "deploy_servicos" {
  statement {
    sid       = "LambdaProjeto"
    actions   = ["lambda:*"]
    resources = local.arns.lambda
  }
  statement {
    sid       = "LambdaListagens"
    actions   = ["lambda:ListFunctions", "lambda:ListLayers", "lambda:ListEventSourceMappings", "lambda:CreateEventSourceMapping", "lambda:GetEventSourceMapping", "lambda:UpdateEventSourceMapping", "lambda:DeleteEventSourceMapping", "lambda:GetAccountSettings"]
    resources = ["*"]
  }
  statement {
    sid       = "DynamoDBProjeto"
    actions   = ["dynamodb:*"]
    resources = local.arns.dynamodb
  }
  statement {
    sid       = "DynamoDBListagens"
    actions   = ["dynamodb:ListTables", "dynamodb:DescribeLimits"]
    resources = ["*"]
  }
  statement {
    sid       = "ApiGatewayProjeto"
    actions   = ["apigateway:*"]
    resources = local.arns.apigateway
  }
  statement {
    sid       = "CognitoProjeto"
    actions   = ["cognito-idp:*"]
    resources = local.arns.cognito
  }
  statement {
    sid       = "CognitoCriacao"
    actions   = ["cognito-idp:CreateUserPool", "cognito-idp:ListUserPools", "cognito-idp:DescribeUserPoolDomain"]
    resources = ["*"]
  }
  statement {
    sid       = "MensageriaProjeto"
    actions   = ["sns:*", "sqs:*"]
    resources = local.arns.mensageria
  }
  statement {
    sid       = "StepFunctionsValidacao"
    actions   = ["states:ValidateStateMachineDefinition", "states:ListStateMachines"]
    resources = ["*"]
  }
  statement {
    sid       = "OrquestracaoProjeto"
    actions   = ["states:*", "scheduler:*"]
    resources = local.arns.orquestracao
  }
}

data "aws_iam_policy_document" "deploy_observabilidade_e_estado" {
  statement {
    sid       = "LogsProjeto"
    actions   = ["logs:*"]
    resources = local.arns.logs
  }
  statement {
    sid       = "LogsEntregaEListagens"
    actions   = ["logs:CreateLogDelivery", "logs:GetLogDelivery", "logs:UpdateLogDelivery", "logs:DeleteLogDelivery", "logs:ListLogDeliveries", "logs:PutResourcePolicy", "logs:DescribeResourcePolicies", "logs:DescribeLogGroups"]
    resources = ["*"]
    condition {
      test     = "StringEqualsIfExists"
      variable = "aws:RequestedRegion"
      values   = [local.regiao]
    }
  }
  statement {
    sid       = "XrayProjeto"
    actions   = ["xray:*"]
    resources = local.arns.xray
  }
  statement {
    sid       = "XrayListagens"
    actions   = ["xray:GetSamplingRules", "xray:GetSamplingTargets", "xray:GetSamplingStatisticSummaries"]
    resources = ["*"]
  }
  statement {
    sid       = "CloudWatchProjeto"
    actions   = ["cloudwatch:*"]
    resources = local.arns.cloudwatch
  }
  statement {
    sid       = "CloudWatchListagens"
    actions   = ["cloudwatch:DescribeAlarms", "cloudwatch:ListDashboards", "cloudwatch:ListMetrics"]
    resources = ["*"]
    condition {
      test     = "StringEqualsIfExists"
      variable = "aws:RequestedRegion"
      values   = [local.regiao]
    }
  }
  statement {
    sid       = "ParametrosProjeto"
    actions   = ["ssm:*"]
    resources = local.arns.ssm
  }
  statement {
    sid       = "ParametrosListagem"
    actions   = ["ssm:DescribeParameters"]
    resources = ["*"]
  }
  statement {
    sid       = "State"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.state.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["envs/${local.cfg.ambiente}/terraform.tfstate", "envs/${local.cfg.ambiente}/terraform.tfstate.tflock"]
    }
  }
  statement {
    sid       = "StateDoAmbiente"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.state.arn}/envs/${local.cfg.ambiente}/terraform.tfstate"]
  }
  statement {
    sid       = "LockDoAmbiente"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.state.arn}/envs/${local.cfg.ambiente}/terraform.tfstate.tflock"]
  }
}

data "aws_iam_policy_document" "deploy_frontend_e_iam" {
  statement {
    sid       = "FrontendBucket"
    actions   = ["s3:CreateBucket", "s3:DeleteBucket", "s3:Get*", "s3:List*", "s3:Put*", "s3:Delete*"]
    resources = local.arns.site_bucket
  }
  # A distribuicao e criada com tags (default_tags do provider): a condicao vale para a criacao e o TagResource inicial.
  statement {
    sid       = "CloudFrontCriarDistribuicao"
    actions   = ["cloudfront:CreateDistribution", "cloudfront:CreateDistributionWithTags", "cloudfront:TagResource"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/projeto"
      values   = ["revenda"]
    }
  }
  statement {
    sid       = "CloudFrontCriarRecursos"
    actions   = ["cloudfront:CreateFunction", "cloudfront:CreateOriginAccessControl", "cloudfront:CreateResponseHeadersPolicy"]
    resources = ["*"]
  }
  # Somente leitura, sem condicao de tag: ao excluir, o Terraform consulta a distribuicao ate ela sumir, e o recurso ja nao tem tags.
  statement {
    sid       = "CloudFrontLerDistribuicao"
    actions   = ["cloudfront:GetDistribution", "cloudfront:GetDistributionConfig"]
    resources = ["arn:aws:cloudfront::${local.conta}:distribution/*"]
  }
  statement {
    sid       = "CloudFrontGerirDistribuicao"
    actions   = ["cloudfront:UpdateDistribution", "cloudfront:DeleteDistribution", "cloudfront:CreateInvalidation", "cloudfront:GetInvalidation", "cloudfront:TagResource", "cloudfront:UntagResource", "cloudfront:ListTagsForResource"]
    resources = ["arn:aws:cloudfront::${local.conta}:distribution/*"]
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/projeto"
      values   = ["revenda"]
    }
  }
  # Funcoes, controles de acesso e policies de headers nao aceitam tag de recurso; policies de headers usam ID no ARN.
  statement {
    sid       = "CloudFrontGerirFuncoes"
    actions   = ["cloudfront:UpdateFunction", "cloudfront:PublishFunction", "cloudfront:DeleteFunction", "cloudfront:DescribeFunction", "cloudfront:GetFunction", "cloudfront:GetFunctionConfig", "cloudfront:TestFunction", "cloudfront:TagResource", "cloudfront:UntagResource", "cloudfront:ListTagsForResource"]
    resources = ["arn:aws:cloudfront::${local.conta}:function/${local.prefixo}-*"]
  }
  statement {
    sid       = "CloudFrontGerirControlesEHeaders"
    actions   = ["cloudfront:UpdateOriginAccessControl", "cloudfront:DeleteOriginAccessControl", "cloudfront:GetOriginAccessControl", "cloudfront:GetOriginAccessControlConfig", "cloudfront:UpdateResponseHeadersPolicy", "cloudfront:DeleteResponseHeadersPolicy", "cloudfront:GetResponseHeadersPolicy", "cloudfront:GetResponseHeadersPolicyConfig"]
    resources = ["arn:aws:cloudfront::${local.conta}:origin-access-control/*", "arn:aws:cloudfront::${local.conta}:response-headers-policy/*"]
  }
  # Os data sources do modulo frontend buscam as policies gerenciadas do CloudFront pelo nome; o e2e lista as distribuicoes.
  statement {
    sid       = "CloudFrontLeituras"
    actions   = ["cloudfront:ListCachePolicies", "cloudfront:GetCachePolicy", "cloudfront:GetCachePolicyConfig", "cloudfront:ListOriginRequestPolicies", "cloudfront:GetOriginRequestPolicy", "cloudfront:GetOriginRequestPolicyConfig", "cloudfront:ListDistributions", "cloudfront:ListFunctions", "cloudfront:ListOriginAccessControls", "cloudfront:ListResponseHeadersPolicies"]
    resources = ["*"]
  }
  statement {
    sid       = "LeituraDeConta"
    actions   = ["sts:GetCallerIdentity", "iam:GetPolicy", "iam:GetPolicyVersion", "iam:ListPolicyVersions", "iam:GetOpenIDConnectProvider", "kms:DescribeKey", "kms:ListAliases"]
    resources = ["*"]
  }
  # Roles das Lambdas/Step Functions/Scheduler: sempre com a boundary.
  statement {
    sid       = "IamCriarRolesComBoundary"
    actions   = ["iam:CreateRole", "iam:PutRolePermissionsBoundary"]
    resources = local.arns.roles
    condition {
      test     = "StringEquals"
      variable = "iam:PermissionsBoundary"
      values   = [aws_iam_policy.boundary.arn]
    }
  }
  statement {
    sid = "IamManterRoles"
    actions = [
      "iam:GetRole", "iam:DeleteRole", "iam:UpdateRole", "iam:TagRole", "iam:UntagRole", "iam:ListRoleTags",
      "iam:PutRolePolicy", "iam:DeleteRolePolicy", "iam:GetRolePolicy", "iam:ListRolePolicies",
      "iam:ListAttachedRolePolicies", "iam:ListInstanceProfilesForRole", "iam:UpdateAssumeRolePolicy",
    ]
    resources = local.arns.roles
  }
  statement {
    sid       = "IamPassarRoles"
    actions   = ["iam:PassRole"]
    resources = local.arns.roles
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["lambda.amazonaws.com", "states.amazonaws.com", "scheduler.amazonaws.com"]
    }
  }
  statement {
    sid       = "IamNaoRemoverBoundary"
    effect    = "Deny"
    actions   = ["iam:DeleteRolePermissionsBoundary", "iam:AttachRolePolicy", "iam:DetachRolePolicy"]
    resources = ["*"]
  }
}

# Uma policy gerenciada por grupo: o limite de 6144 caracteres vale por policy, e o das inline, 10240 por role.
locals {
  politicas_deploy = {
    servicos                 = data.aws_iam_policy_document.deploy_servicos.json
    observabilidade_e_estado = data.aws_iam_policy_document.deploy_observabilidade_e_estado.json
    frontend_e_iam           = data.aws_iam_policy_document.deploy_frontend_e_iam.json
  }
}

resource "aws_iam_policy" "deploy" {
  for_each = local.politicas_deploy

  name   = "gha-deploy-${local.cfg.ambiente}-${replace(each.key, "_", "-")}"
  policy = each.value
}

resource "aws_iam_role_policy_attachment" "deploy" {
  for_each = aws_iam_policy.deploy

  role       = aws_iam_role.deploy.name
  policy_arn = each.value.arn
}



# Role somente-leitura para o `terraform plan` de PRs de branches do proprio repositorio.
data "aws_iam_policy_document" "confianca_plan" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [for r in local.repo_oidc_subs : "${r}:pull_request"]
    }
  }
}

resource "aws_iam_role" "plan" {
  name                 = "gha-plan-${local.cfg.ambiente}"
  assume_role_policy   = data.aws_iam_policy_document.confianca_plan.json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "plan" {
  statement {
    sid       = "LeituraLambda"
    actions   = ["lambda:Get*", "lambda:List*"]
    resources = concat(local.arns.lambda, ["*"])
  }
  statement {
    sid       = "LeituraDynamoDB"
    actions   = ["dynamodb:Describe*", "dynamodb:List*"]
    resources = local.arns.dynamodb
  }
  statement {
    sid       = "LeituraApiGateway"
    actions   = ["apigateway:GET"]
    resources = local.arns.apigateway
  }
  statement {
    sid       = "LeituraCognito"
    actions   = ["cognito-idp:Describe*", "cognito-idp:GetUserPoolMfaConfig", "cognito-idp:GetGroup", "cognito-idp:ListGroups", "cognito-idp:ListUserPoolClients", "cognito-idp:ListTagsForResource"]
    resources = local.arns.cognito
  }
  statement {
    sid       = "LeituraMensageria"
    actions   = ["sns:Get*", "sns:List*", "sqs:Get*", "sqs:List*"]
    resources = local.arns.mensageria
  }
  statement {
    sid       = "LeituraOrquestracao"
    actions   = ["states:Describe*", "states:ListTagsForResource", "scheduler:Get*", "scheduler:List*"]
    resources = local.arns.orquestracao
  }
  statement {
    sid       = "LeituraLogs"
    actions   = ["logs:ListTagsForResource", "logs:ListTagsLogGroup"]
    resources = local.arns.logs
  }
  statement {
    sid       = "LeituraObservabilidadeEListagens"
    actions   = ["logs:DescribeLogGroups", "cloudwatch:Describe*", "cloudwatch:Get*", "cloudwatch:List*", "xray:Get*", "xray:ListTagsForResource"]
    resources = ["*"]
    condition {
      test     = "StringEqualsIfExists"
      variable = "aws:RequestedRegion"
      values   = [local.regiao]
    }
  }
  statement {
    sid       = "LeituraParametros"
    actions   = ["ssm:GetParameter", "ssm:GetParameters", "ssm:ListTagsForResource"]
    resources = local.arns.ssm
  }
  statement {
    sid       = "LeituraParametrosListagem"
    actions   = ["ssm:DescribeParameters"]
    resources = ["*"]
  }
  statement {
    sid       = "LeituraIdentidadeEKms"
    actions   = ["sts:GetCallerIdentity", "kms:DescribeKey", "kms:ListAliases"]
    resources = ["*"]
  }
  statement {
    sid       = "LeituraIam"
    actions   = ["iam:GetRole", "iam:GetRolePolicy", "iam:ListRolePolicies", "iam:ListAttachedRolePolicies", "iam:ListRoleTags", "iam:GetPolicy", "iam:GetPolicyVersion", "iam:ListPolicyVersions", "iam:ListPolicyTags", "iam:GetOpenIDConnectProvider"]
    resources = concat(local.arns.roles, ["arn:aws:iam::${local.conta}:policy/${local.prefixo}-*", "arn:aws:iam::${local.conta}:oidc-provider/token.actions.githubusercontent.com"])
  }
  statement {
    sid       = "LeituraFrontend"
    actions   = ["s3:Get*", "s3:List*"]
    resources = local.arns.site_bucket
  }
  statement {
    sid       = "LeituraCloudFront"
    actions   = ["cloudfront:Get*", "cloudfront:List*", "cloudfront:Describe*"]
    resources = ["*"]
  }
  statement {
    sid       = "ListarStateAmbiente"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.state.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["envs/${local.cfg.ambiente}/terraform.tfstate", "envs/${local.cfg.ambiente}/terraform.tfstate.tflock"]
    }
  }
  statement {
    sid       = "LerStateAmbiente"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.state.arn}/envs/${local.cfg.ambiente}/terraform.tfstate"]
  }
  statement {
    sid       = "LockPlanoAmbiente"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.state.arn}/envs/${local.cfg.ambiente}/terraform.tfstate.tflock"]
  }
}

resource "aws_iam_role_policy" "plan" {
  name   = "plano"
  role   = aws_iam_role.plan.id
  policy = data.aws_iam_policy_document.plan.json
}
