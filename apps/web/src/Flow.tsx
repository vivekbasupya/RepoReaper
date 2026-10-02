import { ReactFlow, Background, type Node } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
export default function Flow({ status }: {status: string}) {
 const steps = ['Investigate', 'Reproduce', 'Patch', 'Verify', 'Review'];
 const nodes: Node[] = steps.map((s,i) => ({id:String(i),position:{x:i*155,y:20},data:{label:s},style:{background:'#20232e',color:'#ededf4',borderColor: status === 'needs_review' ? '#6dbfa0':'#57526d',width:130,borderRadius:10}}));
 return <div style={{height:150}} role="img" aria-label={`Workflow: ${steps.join(', ')}. Current state ${status}`}><ReactFlow nodes={nodes} edges={steps.slice(1).map((_,i)=>({id:`${i}`,source:String(i),target:String(i+1)}))} nodesDraggable={false} nodesConnectable={false} elementsSelectable={false} fitView proOptions={{hideAttribution:true}}><Background/></ReactFlow></div>;
}
