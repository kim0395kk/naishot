# -*- coding: utf-8 -*-
"""
Export module for document generation
"""
from .docx_generator import DOCXGenerator, generate_official_docx, generate_guide_docx

__all__ = ['DOCXGenerator', 'generate_official_docx', 'generate_guide_docx']
