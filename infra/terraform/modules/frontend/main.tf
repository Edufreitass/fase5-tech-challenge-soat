# Frontend estatico: S3 privado (OAC) + CloudFront. A API entra pelo mesmo dominio em /api/* (sem CORS).
variable "prefixo" {
  type = string
}

variable "regiao" {
  type = string
}

variable "api_id" {
  description = "ID do API Gateway REST."
  type        = string
}

variable "api_stage" {
  type = string
}

resource "random_string" "sufixo" {
  length  = 6
  upper   = false
  special = false
}

locals {
  bucket     = "${var.prefixo}-web-${random_string.sufixo.result}"
  origem_api = "${var.api_id}.execute-api.${var.regiao}.amazonaws.com"
}

resource "aws_s3_bucket" "web" {
  bucket        = local.bucket
  force_destroy = true # o destroy do ambiente precisa funcionar com o site publicado
}

resource "aws_s3_bucket_public_access_block" "web" {
  bucket                  = aws_s3_bucket.web.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "web" {
  bucket = aws_s3_bucket.web.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "web" {
  bucket = aws_s3_bucket.web.id
  rule {
    id     = "abortar-uploads-incompletos"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

resource "aws_cloudfront_origin_access_control" "web" {
  name                              = "${var.prefixo}-web"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# SPA: qualquer caminho sem extensao devolve index.html (o fallback global mascararia os 403/404 da API).
resource "aws_cloudfront_function" "spa" {
  name    = "${var.prefixo}-spa"
  runtime = "cloudfront-js-2.0"
  publish = true
  code    = <<-JS
    function handler(event) {
      var req = event.request;
      if (req.uri.indexOf('.') === -1) { req.uri = '/index.html'; }
      return req;
    }
  JS
}

resource "aws_cloudfront_function" "api" {
  name    = "${var.prefixo}-api-prefixo"
  runtime = "cloudfront-js-2.0"
  publish = true
  code    = <<-JS
    function handler(event) {
      var req = event.request;
      req.uri = req.uri.replace(/^\/api/, '') || '/';
      return req;
    }
  JS
}

resource "aws_cloudfront_response_headers_policy" "seguranca" {
  name = "${var.prefixo}-seguranca"
  security_headers_config {
    strict_transport_security {
      access_control_max_age_sec = 31536000
      include_subdomains         = true
      preload                    = true
      override                   = true
    }
    content_type_options {
      override = true
    }
    frame_options {
      frame_option = "DENY"
      override     = true
    }
    referrer_policy {
      referrer_policy = "same-origin"
      override        = true
    }
    content_security_policy {
      override                = true
      content_security_policy = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self' https://cognito-idp.${var.regiao}.amazonaws.com; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    }
  }
}

# Politicas gerenciadas: cache otimizado para o site; sem cache e sem Host para a API.
data "aws_cloudfront_cache_policy" "otimizada" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_cache_policy" "desligada" {
  name = "Managed-CachingDisabled"
}

data "aws_cloudfront_origin_request_policy" "api" {
  name = "Managed-AllViewerExceptHostHeader"
}

resource "aws_cloudfront_distribution" "web" {
  enabled             = true
  comment             = "${var.prefixo} frontend"
  default_root_object = "index.html"
  price_class         = "PriceClass_100"
  http_version        = "http2and3"

  origin {
    origin_id                = "s3"
    domain_name              = aws_s3_bucket.web.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.web.id
  }

  origin {
    origin_id   = "api"
    domain_name = local.origem_api
    origin_path = "/${var.api_stage}"
    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id           = "s3"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD", "OPTIONS"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = data.aws_cloudfront_cache_policy.otimizada.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.seguranca.id
    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.spa.arn
    }
  }

  ordered_cache_behavior {
    path_pattern             = "/api/*"
    target_origin_id         = "api"
    viewer_protocol_policy   = "https-only"
    allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods           = ["GET", "HEAD"]
    compress                 = true
    cache_policy_id          = data.aws_cloudfront_cache_policy.desligada.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.api.id
    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.api.arn
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

data "aws_iam_policy_document" "bucket" {
  statement {
    sid       = "SomenteCloudFront"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.web.arn}/*"]
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.web.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "web" {
  bucket     = aws_s3_bucket.web.id
  policy     = data.aws_iam_policy_document.bucket.json
  depends_on = [aws_s3_bucket_public_access_block.web]
}

output "dominio" {
  value = aws_cloudfront_distribution.web.domain_name
}

output "url" {
  value = "https://${aws_cloudfront_distribution.web.domain_name}"
}

output "bucket" {
  value = aws_s3_bucket.web.id
}

output "distribuicao_id" {
  value = aws_cloudfront_distribution.web.id
}
