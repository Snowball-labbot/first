function v10_figures(root,skillRoot,only)
% V10 final 12 figures: frozen V8 evidence, user-selected proportions and colors.
% Former figures 10 and 14 were removed; old figure 13 is now figure 12.
% Optional ONLY is a cell array of figure names for targeted visual revisions.
if nargin<3,only={};end
cd(root);addpath(fullfile(skillRoot,'references','roles','编程手','scripts'));
D=load('artifacts/v8/figure_data.mat');out='figures/v10';if ~isfolder(out),mkdir(out);end
C.grid=hex('#4D779B');C.soc=hex('#8074C8');C.price=hex('#8D2F25');C.base=hex('#9D9EA3');
C.emergency=hex('#992224');C.orange=hex('#EF8B67');C.gold=hex('#F0C284');C.pale=hex('#A8CBDF');
C.load=hex('#3E608D');C.charge=hex('#7AB656');C.actual=hex('#CD3B42');
h=D.hours(:)';edges=0:1/6:24;
dates={'3月20日','6月21日','9月23日','12月21日'};
% Independent MATLAB optimization uses inequality supply balance, without
% the Python solver's explicit spill variable.
if isempty(only) && exist('linprog','file')==2
 n=144;cost=[D.q1_price(:);zeros(3*n+1,1)];A=sparse(n,4*n+1);
 for t=1:n,A(t,t)=-1;A(t,n+t)=1;A(t,2*n+t)=-1;end
 rhs=D.q1_pv_kwh(:)-D.q1_load_kwh(:);E=sparse(n,4*n+1);
 for t=1:n,E(t,3*n+t+1)=1;E(t,3*n+t)=-1;E(t,n+t)=-.9;E(t,2*n+t)=1/.9;end
 lb=[zeros(3*n,1);1200*ones(n+1,1)];ub=[inf(n,1);(5000/6)*ones(2*n,1);10800*ones(n+1,1)];
 lb(3*n+1)=6000;ub(3*n+1)=6000;lb(end)=6000;ub(end)=6000;
 [~,v,flag]=linprog(cost,A,rhs,E,zeros(n,1),lb,ub,optimoptions('linprog','Display','none'));
 assert(flag>0 && abs(v-D.q1_waterfall(3)*1e4)<1e-6);
 writejson('artifacts/v10/matlab_q1_audit.json',struct('cost_yuan',v,'exitflag',flag,'passed',true));
elseif isempty(only)
 v=sum(D.q1_price.*D.q1_plan_kwh);
 assert(abs(v-D.q1_waterfall(3)*1e4)<1e-6);
 writejson('artifacts/v10/matlab_q1_audit.json',struct('cost_yuan',v,'bill_recomputed',true,...
  'optimization_replayed',false,'reason','Optimization Toolbox unavailable; LP and MILP audited by src/v8_prepare.py'));
end

if wanted(only,'modeling_overview')
 f=fig(3.2);a=axes(f,'Position',[.055 .075 .91 .85]);axis(a,[0 100 0 100]);axis(a,'off');hold(a,'on');
 box(a,[1 81 18 16],{'原始附件','时段与单位统一'});
 box(a,[1 51 18 16],{'共同物理模型','能量平衡与储能递推'});
 box(a,[1 21 18 16],{'实际费用评价','计划 · 调单 · 补购'});
 arrow(a,[10 81],[10 67]);arrow(a,[10 51],[10 37]);
 ys=[89 63 37 11];
 qs={'问题一','问题二','问题三','问题四'};
 inputs={{'供需与电价已知'},{'引入供需预测误差'},{'引入预报更新与调单'},{'引入波动电价与预测误差'}};
 methods={{'确定性线性规划','购电与储能联合优化'},{'预测 + 风险校准','固定合同库存价值控制'},...
 {'非对称结算滚动优化','可调单库存价值控制'},{'第二问日前分支 / 第三问滚动分支','预测价格决策，实际价格结算'}};
 for k=1:4
  box(a,[24 ys(k)-6 12 12],qs(k));box(a,[40 ys(k)-6 24 12],inputs{k});box(a,[68 ys(k)-8 31 16],methods{k});
  arrow(a,[36 ys(k)],[40 ys(k)]);arrow(a,[64 ys(k)],[68 ys(k)]);
 end
 plot(a,[19 22 22],[59 59 89],'k-','LineWidth',.7);plot(a,[22 22],[59 11],'k-','LineWidth',.7);
 for y=ys,arrow(a,[22 y],[24 y]);end
 for k=1:3,arrow(a,[84 ys(k)-8],[84 ys(k+1)+8]);end
 saveout(f,out,'modeling_overview');
end

if wanted(only,'raw_q1_inputs')

 f=fig(7.9/2.54);a=ax(f,[.11 .44 .85 .43]);panel(a,'a','供需曲线');
 steparea(a,edges,D.q1_pv_kwh*6/1000,hex('#FBE4B6'),1);
 stairs(a,edges,[D.q1_load_kwh D.q1_load_kwh(end)]*6/1000,'Color',C.load,'LineWidth',1.1);
 set(a,'XLim',[0 24],'XTick',0:6:24,'XTickLabel',[],'YLim',[0 8.5]);ylabel(a,'功率 / MW');
 legend(a,{'光伏','负载'},'Orientation','horizontal','Box','off','Location','northwest');
 b=ax(f,[.11 .16 .85 .17]);panel(b,'b','分时电价');
 stairs(b,edges,[D.q1_price D.q1_price(end)],'Color',C.price,'LineWidth',1);
 set(b,'XLim',[0 24],'XTick',0:6:24,'YLim',[.3 1.55],'YTick',[.5 1 1.5]);ylabel(b,'元/kWh');xlabel(b,'时刻 / h');
 saveout(f,out,'raw_q1_inputs');
end

if wanted(only,'result_q1_dispatch')

 f=fig(11.39172/2.54);a=ax(f,[.105 .55 .85 .34]);
 steparea(a,edges,D.q1_charge_kwh*6/1000,C.charge,.42);
 steparea(a,edges,-D.q1_discharge_kwh*6/1000,C.orange,.60);
 stairs(a,edges,[D.q1_plan_kwh D.q1_plan_kwh(end)]*6/1000,'Color',C.grid,'LineWidth',1.05);
 stairs(a,edges,[D.q1_load_kwh D.q1_load_kwh(end)]*6/1000,'--','Color',C.load,'LineWidth',.8);
 stairs(a,edges,[D.q1_pv_kwh D.q1_pv_kwh(end)]*6/1000,'Color',hex('#C58A26'),'LineWidth',.85);
 yline(a,0,'k-','HandleVisibility','off');
 set(a,'XLim',[0 24],'XTick',0:4:24,'XTickLabel',[],'YLim',[-5 10],'YTick',[-5 0 5 10]);ylabel(a,'功率 / MW');
 text(a,.01,.95,'a','Units','normalized','FontWeight','bold','VerticalAlignment','top');
 lg=legend(a,{'充电','放电','外网购电','负载','光伏'},'Orientation','horizontal','Box','off','FontSize',7.6);lg.Position=[.17 .935 .76 .045];
 b=ax(f,[.105 .30 .85 .18]);panel(b,'b','储能状态');
 plot(b,edges,[D.q1_soc_start_kwh D.q1_soc_end_kwh(end)]/1000,'Color',C.soc,'LineWidth',1.2);
 for y=[1.2 10.8],yline(b,y,':','Color',[.45 .45 .45]);end
 set(b,'XLim',[0 24],'XTick',0:4:24,'XTickLabel',[],'YLim',[0 12],'YTick',[1.2 6 10.8]);ylabel(b,'储电量 / MWh');
 c=ax(f,[.105 .11 .85 .115]);panel(c,'c','价格信号');
 stairs(c,edges,[D.q1_price D.q1_price(end)],'Color',C.price,'LineWidth',1);
 set(c,'XLim',[0 24],'XTick',0:4:24,'YLim',[.3 1.6],'YTick',[.5 1 1.5]);ylabel(c,'元/kWh');xlabel(c,'时刻 / h');
 saveout(f,out,'result_q1_dispatch');
end

if wanted(only,'q1_efficiency')

 f=fig(3.05);a=ax(f,[.15 .22 .36 .61]);panel(a,'a','储能费用');
 v=D.q1_waterfall([1 3 2]);b=barh(a,1:3,v,.46,'FaceColor','flat','EdgeColor','none');
 b.CData=[.67 .68 .69;.38 .49 .57;.80 .81 .82];
 for k=1:3,text(a,.14,k,sprintf('%.2f 元',v(k)*1e4),'FontSize',8,'VerticalAlignment','middle');end
 set(a,'YDir','reverse','YTick',1:3,'YTickLabel',{'无储能','实际效率','无损储能'},'YLim',[.4 3.6],'XLim',[0 5.3],'XTick',[0 2 4]);
 a.YGrid='off';a.XGrid='on';xlabel(a,'日费用 / 万元');
 b=ax(f,[.70 .22 .26 .61]);panel(b,'b','效率响应');
 plot(b,D.q1_efficiency,D.q1_sensitivity,'-o','Color',C.grid,'MarkerFaceColor','w','MarkerSize',4,'LineWidth',1.1);
 scatter(b,81,D.q1_sensitivity(3),55,'k','LineWidth',.8);
 text(b,83,3.57,'81%','FontSize',8);
 set(b,'XLim',[62 103],'YLim',[3.15 3.98],'XTick',[64 81 100],'YTick',3.2:.2:3.8);
 xlabel(b,'往返效率 / %');ylabel(b,'日费用 / 万元');saveout(f,out,'q1_efficiency');
end

if wanted(only,'q2_validation')
 f=fig(2.5);axeslist=gobjects(1,2);colors=[C.base;C.grid];styles={'--o','-s'};
 for j=1:2
  a=ax(f,[.095+(j-1)*.48 .24 .38 .52]);axeslist(j)=a;
  if j==1,vals=D.validation_cost;ttl='总费用';yl=[46 72];else,vals=D.validation_emergency;ttl='紧急购电费';yl=[-.5 19];end
  for k=1:2,plot(a,1:4,vals(k,:),styles{k},'Color',colors(k,:),'MarkerFaceColor','w','MarkerSize',4,'LineWidth',1);end
  set(a,'XLim',[.75 4.25],'XTick',1:4,'XTickLabel',{'无余量','70%','80%','90%'},'YLim',yl);
  xlabel(a,'误差余量分位数');ylabel(a,'验证期费用 / 万元');panel(a,char('a'+j-1),ttl);
 end
 a=axeslist(1);scatter(a,2,D.validation_cost(2,2),52,'k','o','LineWidth',.8);
 text(a,2,48.2,'50.98','HorizontalAlignment','center','FontSize',8);
 lg=legend(a,{'同期预测','岭回归'},'Orientation','horizontal','Box','off','FontSize',8);lg.Position=[.33 .94 .4 .06];
 saveout(f,out,'q2_validation');
end

if wanted(only,'q2_forecasts')

 f=fig(16.368/2.54);
 for k=1:4
  for j=1:2
   a=ax(f,[.11+(j-1)*.47 .77-(k-1)*.215 .375 .155]);
   if j==1,obs=D.q2_load_kwh;pred=D.q2_forecast_load_kwh;yl=9;unit='负载 / MW';else,obs=D.q2_pv_kwh;pred=D.q2_forecast_pv_kwh;yl=11;unit='光伏 / MW';end
   plot(a,h,obs(k,:)*6/1000,'Color',[.25 .25 .25],'LineWidth',.85);
   plot(a,h,pred(k,:)*6/1000,'--','Color',C.grid,'LineWidth',1);
   set(a,'XLim',[0 24],'XTick',0:6:24,'YLim',[0 yl]);
   panel(a,char('a'+(k-1)*2+j-1),dates{k});ylabel(a,unit);
   if k==4,xlabel(a,'时刻 / h');else,a.XTickLabel={};end
   if k==1&&j==1,lg=legend(a,{'实际','日前预测'},'Orientation','horizontal','Box','off');lg.Position=[.34 .967 .36 .025];end
  end
 end
 saveout(f,out,'q2_forecasts');
end

if wanted(only,'q2_cost')

 f=fig(3.35);ids=[1 2 4 5];tot=sum(D.q2_cost(ids,:),2);sv=-diff(tot);
 a=ax(f,[.14 .20 .79 .70]);
 starts=[0;tot(2:4);0];heights=[tot(1);sv;tot(4)];
 colors=[.72 .75 .77;.39 .59 .64;.48 .67 .68;.76 .55 .43;.23 .40 .52];
 for k=1:5
  rectangle(a,'Position',[k-.30 starts(k) .60 heights(k)],'FaceColor',colors(k,:),'EdgeColor','none');
  if k==1||k==5,label=sprintf('%.2f',heights(k));else,label=sprintf('−%.2f',heights(k));end
  text(a,k,starts(k)+heights(k)+90,label,'FontSize',8.5,'HorizontalAlignment','center');
 end
 for k=1:4,plot(a,[k+.30 k+.70],[tot(k) tot(k)],':','Color',[.55 .57 .59],'LineWidth',.7);end
 set(a,'XLim',[.4 5.6],'YLim',[0 2280],'YTick',[0 500 1000 1500 2000],'XTick',1:5,'XTickLabel',{'同期基线','岭回归预测','70%风险余量','库存价值控制','最终费用'});
 ylabel(a,'334天费用 / 万元');
 saveout(f,out,'q2_cost');
end

if wanted(only,'q3_forecasts')
 f=fig(8.07339/2.54);a=ax(f,[.10 .18 .85 .65]);panel(a,'a','6月21日的光伏预报更新');
 colors=[C.base;C.grid;C.load;C.soc];lines=gobjects(1,5);
 lines(1)=plot(a,h,D.q3_pv_actual,'Color',C.actual,'LineWidth',1.2);
 for k=1:4
  first=(k-1)*36+1;lines(k+1)=plot(a,h(first:end),D.q3_pv_issued(k,first:end),'--','Color',colors(k,:),'LineWidth',.95);
 end
 for t=[6 12 18],xline(a,t,':','Color',[.55 .55 .55],'LineWidth',.5,'HandleVisibility','off');end
 set(a,'XLim',[0 24],'XTick',0:6:24,'YLim',[0 12],'YTick',0:4:12);xlabel(a,'时刻 / h');ylabel(a,'光伏功率 / MW');
 lg=legend(a,lines,{'实际','00点预报','06点预报','12点预报','18点预报'},'Orientation','horizontal','Box','off','FontSize',7.6);lg.Position=[.19 .95 .77 .06];
 saveout(f,out,'q3_forecasts');
end

if wanted(only,'q3_validation')
 f=fig(2.45);a=ax(f,[.095 .25 .51 .53]);panel(a,'a','一月验证费用 / 万元');
 imagesc(a,D.q3_validation);colormap(a,ramp([1 1 1;.64 .80 .90],128));clim(a,[min(D.q3_validation,[],'all') max(D.q3_validation,[],'all')]);
 set(a,'YDir','reverse','XLim',[.5 8.5],'YLim',[.5 3.5],'XTick',1:8,'XTickLabel',{'无','6','12','6+12','18','6+18','12+18','全部'},'YTick',1:3,'YTickLabel',{'0','50%','70%'},'FontSize',7.5);
 for i=1:3,for j=1:8,text(a,j,i,sprintf('%.1f',D.q3_validation(i,j)),'HorizontalAlignment','center','FontSize',7.2);end,end
 rectangle(a,'Position',[7.5 1.5 1 1],'EdgeColor','k','LineWidth',1);
 a.YGrid='off';xlabel(a,'日内预报组合 / h');ylabel(a,'误差余量分位数');
 b=ax(f,[.76 .25 .20 .53]);panel(b,'b','逐次更新');
 plot(b,1:4,D.q3_validation(2,[1 2 4 8]),'-o','Color',C.grid,'MarkerFaceColor','w','MarkerSize',4);
 set(b,'XTick',1:4,'XTickLabel',{'0','+6','+12','+18'});xlabel(b,'新增预报时刻 / h');ylabel(b,'验证费用 / 万元');
 saveout(f,out,'q3_validation');
end



% Reuse the valid V7 price overview and four-date residual panels; make all
% text black and bring fonts/line weights into the V8 publication style.
for name={'annual_price','price_uncertainty'}
 if wanted(only,name{1})
  f=openfig(fullfile('figures/v8',[name{1} '.fig']),'invisible');
  if strcmp(name{1},'price_uncertainty')
   f.Units='inches';f.Position(4)=3.5;
   lg=findall(f,'Type','legend');lg.Position=[.18 .97 .70 .05];
  end
  saveout(f,out,name{1});
 end
end

if wanted(only,'price_dispatch')

 R=load('artifacts/v10/dispatch_distribution.mat');f=fig(3.15);
 a=ax(f,[.12 .20 .72 .66]);
 val=R.rolling_density;z=log10(max(val,.002));
 im=imagesc(a,R.price_centers,R.power_centers,z);im.AlphaData=double(val>0);
 % ColorBrewer YlGnBu: a sequential multi-hue scale, not a diverging scale.
 cols=[hex('#FFFFD9');hex('#EDF8B1');hex('#C7E9B4');hex('#7FCDBB');hex('#41B6C4');hex('#1D91C0');hex('#225EA8');hex('#253494');hex('#081D58')];
 colormap(a,ramp(cols,256));clim(a,log10([.002 10]));
 yline(a,0,'-','Color',[.5 .5 .5],'LineWidth',.65);
 set(a,'YDir','normal','XLim',[0 1.85],'XTick',[0 .4 .8 1.2 1.6],'YLim',[-5.2 5.2],'YTick',[-5 -2.5 0 2.5 5]);a.YGrid='off';
 xlabel(a,'实际电价 / 元每kWh');ylabel(a,'储能功率 / MW（充电 +，放电 −）');
 cb=colorbar(a);cb.Position=[.88 .20 .018 .66];cb.Ticks=log10([.01 .1 1 10]);cb.TickLabels={'0.01','0.1','1','10'};cb.Label.String='活跃时段占比 / %';cb.FontSize=7.5;
 saveout(f,out,'price_dispatch');
end


disp('V10 MATLAB figures complete');
end

function tf=wanted(only,name),tf=isempty(only)||any(strcmp(only,name));end
function f=fig(height)
f=figure('Visible','off','Color','w','Units','inches','Position',[1 1 6.10 height]);
set(f,'DefaultAxesFontName','Microsoft YaHei','DefaultTextFontName','Microsoft YaHei',...
 'DefaultAxesFontSize',8,'DefaultTextFontSize',8,'DefaultTextColor','k',...
 'DefaultTextInterpreter','none','DefaultLegendInterpreter','none','DefaultAxesTickLabelInterpreter','none');
end
function a=ax(f,p)
a=axes(f,'Position',p);hold(a,'on');
set(a,'FontSize',8,'LineWidth',.6,'TickDir','out','Box','off','YGrid','on','GridColor',[.82 .84 .86],'GridAlpha',.35,'Layer','top','XColor','k','YColor','k');
end
function panel(a,letter,title)
text(a,0,1.12,[letter '  ' title],'Units','normalized','FontWeight','bold','FontSize',8.2,'VerticalAlignment','bottom','Color','k');
end
function steparea(a,edges,y,c,alpha)
y=y(:)';x=reshape([edges(1:end-1);edges(2:end)],1,[]);z=repelem(y,2);
fill(a,[x fliplr(x)],[z zeros(size(z))],c,'FaceAlpha',alpha,'EdgeColor','none');
end
function c=hex(s),c=sscanf(s(2:end),'%2x%2x%2x',[1 3])/255;end
function m=ramp(c,n),m=interp1(linspace(0,1,size(c,1)),c,linspace(0,1,n));end
function box(a,p,t)
rectangle(a,'Position',p,'EdgeColor','k','FaceColor','w','LineWidth',.7);
text(a,p(1)+p(3)/2,p(2)+p(4)/2,t,'HorizontalAlignment','center','VerticalAlignment','middle','FontSize',7.5,'Color','k');
end
function arrow(a,p,q)
plot(a,[p(1) q(1)],[p(2) q(2)],'k-','LineWidth',.6);v=(q-p)/norm(q-p);n=[-v(2) v(1)];u=q-.9*v;
patch(a,[q(1) u(1)+.35*n(1) u(1)-.35*n(1)],[q(2) u(2)+.35*n(2) u(2)-.35*n(2)],'k','EdgeColor','none');
end
function writejson(path,value)
fid=fopen(path,'w','n','UTF-8');fwrite(fid,jsonencode(value),'char');fclose(fid);
end
function saveout(f,out,name)
set(findall(f,'Type','text'),'Color','k');
for a=findall(f,'Type','axes')',a.XColor='k';a.YColor='k';end
for lg=findall(f,'Type','legend')',lg.TextColor='k';lg.Box='off';end
for cb=findall(f,'Type','colorbar')',cb.Color='k';end
drawnow;issues=audit_publication_figure(f);
writejson(fullfile(out,[name '_audit.json']),struct('design_issues',{issues},'all_text_black',true,'source','scripts/v10_figures.m'));
export_publication_figure(f,string(fullfile(out,name)),600,true,false);
% Preserve the specified manuscript canvas instead of automatic tight cropping.
exportgraphics(f,fullfile(out,[name '.png']),'Resolution',600,'Padding','figure');
exportgraphics(f,fullfile(out,[name '.svg']),'ContentType','vector','Padding','figure');
im=imread(fullfile(out,[name '.png']));imwrite(rgb2gray(im),fullfile(out,'_qa',[name '_grayscale.png']));
exportgraphics(f,fullfile(out,[name '.pdf']),'ContentType','vector');
savefig(f,fullfile(out,[name '.fig']));close(f);disp(['Exported ' name]);
end
