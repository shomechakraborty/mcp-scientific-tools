# DISCLAIMER AND TERMS OF SERVICE
# By using this tool you agree to the terms at https://yourdomain.com/terms.
# Service provided "as is" without warranty of any kind. Data sourced from
# third-party public APIs and may be incomplete, inaccurate, or outdated.
# NOT professional medical, legal, financial, or safety advice.
# NOT for clinical, safety-critical, or regulated decision-making without
# independent professional verification.
# Operator liability limited to fees paid in the preceding 30 days.
# Users must independently verify all data before relying on it.

"""
Tool: Compound Property Lookup
================================
Queries PubChem and ChEMBL for molecular properties, bioactivity data,
and drug-likeness metrics. Drug discovery agents use this heavily.

Price: $0.01 per call
Target agents: drug discovery pipelines, chemistry research, toxicity screening

APIs used (all free, no key required):
  - PubChem PUG REST API
  - ChEMBL REST API
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import aiohttp

log = logging.getLogger("tool.compound_lookup")

TOOL_NAME        = "compound_lookup"
TOOL_PRICE_USD   = 0.01
TOOL_STRIPE_PRICE = os.getenv("STRIPE_PRICE_COMPOUND", "price_demo_compound")

PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
CHEMBL_BASE  = "https://www.ebi.ac.uk/chembl/api/data"

TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "identifier": {
            "type": "string",
            "description": "Compound identifier: name, CID, SMILES, InChI, or CAS number",
        },
        "id_type": {
            "type": "string",
            "enum": ["name", "cid", "smiles", "inchi", "cas"],
            "description": "Type of identifier provided (default: name)",
            "default": "name",
        },
        "include_bioactivity": {
            "type": "boolean",
            "description": "Include bioactivity data from ChEMBL (slower, default: false)",
            "default": False,
        },
        "properties": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Specific properties to return (default: all)",
        },
    },
    "required": ["identifier"],
}


# ---------------------------------------------------------------------------
# PubChem lookup
# ---------------------------------------------------------------------------

async def _lookup_pubchem(
    session: aiohttp.ClientSession,
    identifier: str,
    id_type: str,
) -> dict:
    """Fetch compound properties from PubChem."""
    namespace_map = {
        "name": "name", "cid": "cid", "smiles": "smiles",
        "inchi": "inchi", "cas": "name",
    }
    namespace = namespace_map.get(id_type, "name")
    encoded = identifier.replace("/", "%2F").replace("+", "%2B")

    props = [
        "MolecularFormula", "MolecularWeight", "CanonicalSMILES",
        "IsomericSMILES", "InChI", "InChIKey", "IUPACName",
        "XLogP", "ExactMass", "MonoisotopicMass", "TPSA",
        "Complexity", "Charge", "HBondDonorCount", "HBondAcceptorCount",
        "RotatableBondCount", "HeavyAtomCount", "IsotopeAtomCount",
        "AtomStereoCount", "DefinedAtomStereoCount",
    ]

    props_url = (
        f"{PUBCHEM_BASE}/compound/{namespace}/{encoded}"
        f"/property/{','.join(props)}/JSON"
    )

    try:
        async with session.get(props_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 404:
                return {"error": f"Compound not found: {identifier}"}
            if resp.status != 200:
                return {"error": f"PubChem returned status {resp.status}"}
            data = await resp.json()

        properties = data.get("PropertyTable", {}).get("Properties", [{}])[0]
        cid = properties.get("CID")

        # Fetch synonyms (common names, trade names)
        synonyms = []
        if cid:
            syn_url = f"{PUBCHEM_BASE}/compound/cid/{cid}/synonyms/JSON"
            try:
                async with session.get(syn_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        syn_data = await resp.json()
                        synonyms = syn_data.get("InformationList", {}).get(
                            "Information", [{}]
                        )[0].get("Synonym", [])[:10]
            except Exception:
                pass

        # Lipinski rule of 5 drug-likeness assessment
        mw = properties.get("MolecularWeight", 0)
        logp = properties.get("XLogP", 0)
        hbd = properties.get("HBondDonorCount", 0)
        hba = properties.get("HBondAcceptorCount", 0)
        lipinski_violations = sum([
            float(mw or 0) > 500,
            float(logp or 0) > 5,
            int(hbd or 0) > 5,
            int(hba or 0) > 10,
        ])

        return {
            "source": "pubchem",
            "cid": cid,
            "iupac_name": properties.get("IUPACName", ""),
            "molecular_formula": properties.get("MolecularFormula", ""),
            "molecular_weight": properties.get("MolecularWeight"),
            "canonical_smiles": properties.get("CanonicalSMILES", ""),
            "inchikey": properties.get("InChIKey", ""),
            "xlogp": properties.get("XLogP"),
            "tpsa": properties.get("TPSA"),
            "hbond_donors": hbd,
            "hbond_acceptors": hba,
            "rotatable_bonds": properties.get("RotatableBondCount"),
            "heavy_atom_count": properties.get("HeavyAtomCount"),
            "complexity": properties.get("Complexity"),
            "charge": properties.get("Charge"),
            "lipinski_violations": lipinski_violations,
            "drug_likeness": "likely drug-like" if lipinski_violations <= 1 else "poor drug-likeness",
            "synonyms": synonyms[:5],
            "pubchem_url": f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}" if cid else None,
        }

    except Exception as exc:
        log.warning("PubChem lookup failed for %s: %s", identifier, exc)
        return {"error": str(exc), "source": "pubchem"}


# ---------------------------------------------------------------------------
# ChEMBL bioactivity lookup
# ---------------------------------------------------------------------------

async def _lookup_chembl(
    session: aiohttp.ClientSession,
    inchikey: Optional[str],
    compound_name: Optional[str],
) -> dict:
    """Fetch bioactivity data from ChEMBL."""
    if not inchikey and not compound_name:
        return {}

    try:
        # Search for the molecule in ChEMBL
        search_term = inchikey or compound_name
        search_url = f"{CHEMBL_BASE}/molecule.json?molecule_structures__standard_inchi_key={search_term}&format=json"
        if not inchikey:
            search_url = f"{CHEMBL_BASE}/molecule/search.json?q={compound_name}&format=json"

        async with session.get(search_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return {}
            data = await resp.json()

        molecules = data.get("molecules", [])
        if not molecules:
            return {}

        mol = molecules[0]
        chembl_id = mol.get("molecule_chembl_id", "")

        # Get approved drugs and mechanism info
        drug_mechanisms = []
        if mol.get("max_phase", 0) and mol.get("max_phase", 0) > 0:
            mech_url = f"{CHEMBL_BASE}/mechanism.json?molecule_chembl_id={chembl_id}&format=json"
            try:
                async with session.get(mech_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        mech_data = await resp.json()
                        for m in mech_data.get("mechanisms", [])[:3]:
                            drug_mechanisms.append({
                                "target": m.get("target_name", ""),
                                "action": m.get("action_type", ""),
                            })
            except Exception:
                pass

        return {
            "source": "chembl",
            "chembl_id": chembl_id,
            "max_phase": mol.get("max_phase"),
            "first_approval": mol.get("first_approval"),
            "oral": mol.get("oral"),
            "parenteral": mol.get("parenteral"),
            "topical": mol.get("topical"),
            "black_box_warning": mol.get("black_box_warning"),
            "natural_product": mol.get("natural_product"),
            "therapeutic_flags": mol.get("therapeutic_flag"),
            "drug_mechanisms": drug_mechanisms,
            "chembl_url": f"https://www.ebi.ac.uk/chembl/compound_report_card/{chembl_id}/",
        }

    except Exception as exc:
        log.warning("ChEMBL lookup failed: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Tool handler
# ---------------------------------------------------------------------------

async def compound_lookup_handler(arguments: dict) -> dict:
    identifier         = arguments.get("identifier", "")
    id_type            = arguments.get("id_type", "name")
    include_bioactivity = arguments.get("include_bioactivity", False)

    if not identifier:
        return {"error": "identifier parameter is required"}

    async with aiohttp.ClientSession() as session:
        pubchem_result = await _lookup_pubchem(session, identifier, id_type)

        chembl_result = {}
        if include_bioactivity and "error" not in pubchem_result:
            chembl_result = await _lookup_chembl(
                session,
                inchikey=pubchem_result.get("inchikey"),
                compound_name=identifier if id_type == "name" else None,
            )

    result = {
        "identifier": identifier,
        "id_type": id_type,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "pubchem": pubchem_result,
    }
    if chembl_result:
        result["chembl"] = chembl_result

    return result


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register(registry) -> None:
    from server import ToolDefinition
    registry.register(ToolDefinition(
        name=TOOL_NAME,
        description=(
            "Look up chemical compound properties from PubChem and ChEMBL. "
            "Returns molecular weight, SMILES, LogP, TPSA, H-bond donors/acceptors, "
            "Lipinski rule-of-5 drug-likeness assessment, synonyms, and optionally "
            "bioactivity and clinical trial phase data."
        ),
        input_schema=TOOL_SCHEMA,
        price_per_call_usd=TOOL_PRICE_USD,
        stripe_price_id=TOOL_STRIPE_PRICE,
        handler=compound_lookup_handler,
        category="chemistry",
    ))


if __name__ == "__main__":
    async def test():
        print("Testing compound_lookup tool...\n")
        result = await compound_lookup_handler({
            "identifier": "aspirin",
            "id_type": "name",
            "include_bioactivity": False,
        })
        print(f"Identifier: {result['identifier']}")
        pc = result.get("pubchem", {})
        if "error" not in pc:
            print(f"  Formula: {pc.get('molecular_formula')}")
            print(f"  MW: {pc.get('molecular_weight')}")
            print(f"  XLogP: {pc.get('xlogp')}")
            print(f"  Drug-likeness: {pc.get('drug_likeness')}")
            print(f"  Synonyms: {pc.get('synonyms', [])[:3]}")
        else:
            print(f"  Result: {pc}")

    asyncio.run(test())
