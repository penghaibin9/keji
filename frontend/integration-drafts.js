export async function readDraftEntry(api,id){
 const [catalog,draft]=await Promise.all([api('/connections/catalog'),api('/connections/'+id+'/draft')]);
 const entry=catalog.items.find(item=>item.connection.id===id);
 if(!entry)throw Error('接口不存在');
 const connection={...draft.connection,_draft_version:draft.draft_version};
 const mappings=connection.mappings||[];
 const data_types=entry.data_types.map(type=>{const typed=mappings.filter(m=>m.data_type===type.data_type),legacy=mappings.filter(m=>!m.data_type);return {...type,mapping_count:(typed.length?typed:legacy).length};});
 return {...entry,connection,data_types};
}

export async function saveDraft(api,connection,config,mappings,values){
 return api('/connections/'+connection.id+'/draft',{method:'PUT',body:{
  expected_version:connection.version,expected_draft_version:connection._draft_version,
  config,mappings,reason:values.reason,basis:values.basis
 }});
}

export async function previewDraft(api,connection,dataType,records,values){
 const body={data_type:dataType,records,reason:values.reason,basis:values.basis};
 if(connection._draft_version){
  body.expected_version=connection.version;body.draft_version=connection._draft_version;
  return api('/connections/'+connection.id+'/draft/preview',{method:'POST',body});
 }
 body.connection_id=connection.id;
 return api('/connections/validate',{method:'POST',body});
}
