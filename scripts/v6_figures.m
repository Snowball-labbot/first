function v6_figures(root,skillRoot)
% Reproducible V6 figures: fixed semantic palette, exact archived V5 results.
cd(root); addpath(fullfile(skillRoot,'references','roles','编程手','scripts'));
D=load('artifacts/v6/figure_data.mat'); out='figures/v6'; if ~isfolder(out),mkdir(out);end
C.base=hex('#9D9EA3');C.grid=hex('#4D779B');C.gru=hex('#8074C8');
C.price=hex('#8D2F25');C.emergency=hex('#992224');C.charge=hex('#7AB656');
C.orange=hex('#EF8B67');C.pale=hex('#A8CBDF');C.gold=hex('#F0C284');
f=makefig(3.65); ax=axes(f,'Position',[.05 .06 .91 .88]);axis(ax,[0 100 0 100]);axis(ax,'off');hold(ax,'on');
% Compact black-and-white logic tree: evidence -> four branches -> decisions.
box(ax,[1 77 16 15],{'原始附件','时间与单位整理'});
box(ax,[1 50 16 15],{'可用信息集','历史误差校准'});
box(ax,[1 23 16 15],{'共同物理模型','能量与库存约束'});
arrow(ax,[9 77],[9 65]);arrow(ax,[9 50],[9 38]);
plot(ax,[17 21 21],[30.5 30.5 88],'k-','LineWidth',.7);
plot(ax,[21 21],[30.5 13],'k-','LineWidth',.7);
ys=[88 63 38 13];
q={'问题一','问题二','问题三','问题四'};
models={{'多期线性规划','连续状态动态规划'}, {'岭回归与风险余量','历史路径库存价值'}, {'非对称结算滚动LP','负载修正与可调单价值'}, {'同期 / 岭回归 / GRU','价格预测与价值控制'}};
results={{'单日最优购电','储能收益与最优性'}, {'日前购电计划','库存转移与补购成本'}, {'日内计划修订','预报更新的经济价值'}, {'日前与滚动对照','价格信息的改进上限'}};
for k=1:4
  box(ax,[25 ys(k)-7 12 14],q(k));box(ax,[43 ys(k)-8 28 16],models{k});box(ax,[77 ys(k)-8 22 16],results{k});
  arrow(ax,[21 ys(k)],[25 ys(k)]);arrow(ax,[37 ys(k)],[43 ys(k)]);arrow(ax,[71 ys(k)],[77 ys(k)]);
end
for k=1:3,arrow(ax,[57 ys(k)-8],[57 ys(k+1)+8],'--');end
savefigs(f,out,'modeling_overview');

f=makefig(2.35);ax=place(f,[.12 .24 .83 .61]);b=bar(ax,1:3,D.q1_cost,.48,'FaceColor','flat','EdgeColor','none');b.CData=[C.base;C.grid;C.gru];
set(ax,'XTick',1:3,'XTickLabel',{'无储能','两侧各90%','往返90%'},'YLim',[0 5.85]);ylabel(ax,'单日购电费用 / 万元');
for i=1:3,text(ax,i,D.q1_cost(i)+.12,sprintf('%.2f',D.q1_cost(i)),'HorizontalAlignment','center','VerticalAlignment','bottom','FontSize',9);end
plot(ax,[1 1 2 2],[5.06 5.20 5.20 3.78],'k-','LineWidth',.65);
text(ax,1.53,5.48,'节省26.90%','HorizontalAlignment','center','FontSize',9,'Color',C.grid);
savefigs(f,out,'q1_efficiency');

f=makefig(2.7); a=place(f,[.10 .25 .38 .61]); b=place(f,[.60 .25 .36 .61]);
markers={'o','s'}; colors=[C.base;C.grid];
for k=1:2
 scatter(a,1:4,D.validation_cost(k,:),28,colors(k,:),markers{k},'filled');
 scatter(b,1:4,D.validation_emergency(k,:),28,colors(k,:),markers{k},'filled');
end
set([a b],'XTick',1:4,'XTickLabel',{'无','70%','80%','90%'},'XLim',[.5 4.5]);
ylabel(a,'验证总费用 / 万元');ylabel(b,'紧急购电费 / 万元');xlabel(a,'误差余量分位数');xlabel(b,'误差余量分位数');
panel(a,'a','总费用');panel(b,'b','紧急补购');ylim(a,[46 72]);ylim(b,[-.6 19]);
scatter(a,2,D.validation_cost(2,2),85,C.grid,'o','LineWidth',1.1);text(a,2.1,48.4,'50.98','FontSize',8,'Color',C.grid);
leg=legend(a,{'同期','岭回归'},'Orientation','horizontal','Box','off','FontSize',8);leg.Units='normalized';leg.Position=[.19 .91 .30 .05];a.Position=[.10 .25 .38 .57];b.Position=[.60 .25 .36 .57];
savefigs(f,out,'q2_validation');

f=makefig(3.7);a=place(f,[.25 .46 .70 .43]); b=barh(a,1:5,D.q2_cost,'stacked','BarWidth',.55,'EdgeColor','none');
b(1).FaceColor=C.grid;b(2).FaceColor=C.emergency;
set(a,'YDir','reverse','YTick',1:5,'YTickLabel',{'同期 无余量','岭回归 无余量','同期 70%余量','岭回归 70%余量','库存价值控制'},'XLim',[0 2160],'XTick',0:500:2000);
xlabel(a,'');a.YGrid='off';a.XGrid='on';
for i=1:5,text(a,sum(D.q2_cost(i,:))+24,i,sprintf('%.2f',sum(D.q2_cost(i,:))),'FontSize',8,'VerticalAlignment','middle');end
legend(a,{'普通计划费','紧急费'},'Location','northoutside','Orientation','horizontal','FontSize',8);
panel(a,'a','334天费用构成 / 万元');
b=place(f,[.25 .13 .70 .19]); plot(b,2:12,cumsum(D.monthly_saving(1,:)),'-o','Color',C.gru,'LineWidth',1.25,'MarkerFaceColor','w','MarkerSize',3.5);
set(b,'XLim',[2 12.7],'XTick',2:2:12,'YLim',[0 16],'YTick',[0 7 14]);ylabel(b,'累计节省 / 万元');xlabel(b,'月份');
panel(b,'b','价值控制的累计收益');text(b,12.15,14.12,'14.12','FontSize',8,'Color',C.gru);
savefigs(f,out,'q2_cost');

f=makefig(2.65);a=place(f,[.09 .24 .50 .57]);imagesc(a,D.q3_validation);set(a,'YDir','reverse','XLim',[.5 8.5],'YLim',[.5 3.5],'XTick',1:8,'XTickLabel',{'无','6','12','6+12','18','6+18','12+18','全部'},'YTick',1:3,'YTickLabel',{'0','50%','70%'},'FontSize',7.5);
colormap(a,ramp([1 1 1;C.pale;C.grid],128));clim(a,[min(D.q3_validation,[],'all') max(D.q3_validation,[],'all')]);
for i=1:3,for j=1:8
 val=D.q3_validation(i,j);col=[.12 .12 .12];if val>58,col=[1 1 1];end
 text(a,j,i,sprintf('%.1f',val),'HorizontalAlignment','center','FontSize',7.3,'Color',col);
end,end
rectangle(a,'Position',[7.5 1.5 1 1],'EdgeColor','k','LineWidth',1.4);xlabel(a,'更新时间 / h');ylabel(a,'风险余量');panel(a,'a','一月验证费用 / 万元');a.XGrid='off';a.YGrid='off';
b=place(f,[.73 .24 .22 .57]);x=1:4;vals=[D.q3_validation(2,1),D.q3_validation(2,2),D.q3_validation(2,4),D.q3_validation(2,8)];
plot(b,x,vals,'-o','Color',C.grid,'MarkerFaceColor','w');set(b,'XTick',1:4,'XTickLabel',{'0','+6','+12','+18'});xtickangle(b,0);ylabel(b,'验证费用 / 万元');panel(b,'b','逐次增加预报');
savefigs(f,out,'q3_validation');

f=makefig(3.55);a=place(f,[.10 .36 .18 .50]);bits=[bitget((0:7)',1),bitget((0:7)',2),bitget((0:7)',3)];imagesc(a,bits);colormap(a,[1 1 1;C.grid]);clim(a,[0 1]);set(a,'XLim',[.5 3.5],'YLim',[.5 8.5],'YDir','reverse','XTick',1:3,'XTickLabel',{'06','12','18'},'YTick',1:8,'YTickLabel',{'无','6','12','6+12','18','6+18','12+18','全部'});a.XGrid='off';a.YGrid='off';a.Box='on';xlabel(a,'更新时刻 / h');panel(a,'a','更新组合');
for i=.5:1:8.5,plot(a,[.5 3.5],[i i],'Color',[.85 .87 .89],'LineWidth',.5);end
for j=.5:1:3.5,plot(a,[j j],[.5 8.5],'Color',[.85 .87 .89],'LineWidth',.5);end
b=place(f,[.40 .36 .54 .50]);s=D.q3_cost(1)-D.q3_cost;h=barh(b,1:8,s,.56,'FaceColor',C.grid,'EdgeColor','none');set(b,'YDir','reverse','YLim',[.5 8.5],'YTick',[],'XLim',[0 175],'XTick',0:50:150);b.YGrid='off';b.XGrid='on';xlabel(b,'相对不更新节省 / 万元');panel(b,'b','基础滚动的全年收益');
for i=1:8,text(b,s(i)+2,i,sprintf('%.2f',s(i)),'VerticalAlignment','middle','FontSize',8);end
c=place(f,[.10 .06 .85 .12]);axis(c,[0 1 0 1]);axis(c,'off');
text(c,0,.85,'最终方案费用 / 万元','FontSize',8,'FontWeight','bold');
text(c,0,.25,sprintf('基础滚动  %.2f',D.q3_evolution(1)),'FontSize',9);
text(c,.37,.25,sprintf('负载选择  %.2f',D.q3_evolution(2)),'FontSize',9);
text(c,.72,.25,sprintf('价值控制  %.2f',D.q3_evolution(3)),'FontSize',9,'Color',C.gru);
savefigs(f,out,'q3_updates');

f=makefig(3.75);a=place(f,[.105 .47 .78 .40]);
imagesc(a,1:365,(.5:143.5)/6,D.price');axis(a,'xy');set(a,'XLim',[.5 365.5],'YLim',[0 24],'XTick',[1 60 121 182 244 305],'XTickLabel',{'1月','3月','5月','7月','9月','11月'},'YTick',0:6:24);ylabel(a,'时刻 / h');panel(a,'a','全年电价的季节与日内结构');
colormap(a,ramp([hex('#FDF9EE');hex('#F5EBAE');C.gold;C.orange;hex('#E3625D');C.emergency],256));clim(a,[0 1.85]);cb=colorbar(a,'Position',[.91 .47 .018 .40]);cb.Label.String='元/kWh';cb.FontSize=8;a.XGrid='off';a.YGrid='off';
b=place(f,[.105 .14 .78 .20]); months=month(datetime(2025,1,1)+days(0:364)); means=zeros(12,1);lo=means;hi=means;
for k=1:12,v=D.price(months==k,:);v=v(:);means(k)=mean(v);lo(k)=quantile(v,.1);hi(k)=quantile(v,.9);end
errorbar(b,1:12,means,means-lo,hi-means,'o','Color',C.price,'MarkerFaceColor',C.price,'MarkerSize',3,'LineStyle','none','CapSize',4,'LineWidth',.85);
set(b,'XLim',[.5 12.5],'XTick',1:12,'YLim',[0 1.8],'YTick',[0 .6 1.2 1.8]);ylabel(b,'电价 / 元每kWh');xlabel(b,'月份');panel(b,'b','月均值与10%—90%分位范围');
savefigs(f,out,'annual_price');

f=makefig(2.6);a=place(f,[.15 .22 .72 .64]);imagesc(a,D.price_mae);
set(a,'YDir','reverse','XTick',1:4,'XTickLabel',{'00:00','06:00','12:00','18:00'},'YTick',1:3,'YTickLabel',{'同期','岭回归','GRU集成'},'XLim',[.5 4.5],'YLim',[.5 3.5]);colormap(a,ramp([1 1 1;C.pale;C.grid],128));clim(a,[.035 .065]);a.XGrid='off';a.YGrid='off';
for i=1:3,for j=1:4,col=[.12 .12 .12];if D.price_mae(i,j)>.055,col=[1 1 1];end;text(a,j,i,sprintf('%.4f',D.price_mae(i,j)),'HorizontalAlignment','center','FontSize',10,'Color',col);end,end
rectangle(a,'Position',[.5 2.5 4 1],'EdgeColor',C.gru,'LineWidth',1.4);xlabel(a,'预测发布时刻');
cb=colorbar(a,'Position',[.90 .22 .021 .64]);cb.Label.String='MAE / 元每kWh';cb.FontSize=8;
savefigs(f,out,'q4_accuracy');

f=makefig(3.7);labels={'同期','岭回归','GRU','真实电价'};
for k=1:2
 a=place(f,[.14+(k-1)*.47 .57 .35 .29]);v=D.q4_cost(k,1)-D.q4_cost(k,:);
 h=barh(a,1:4,v,.54,'FaceColor','flat','EdgeColor','none');h.CData=[C.base;C.grid;C.gru;C.charge];
 set(a,'YDir','reverse','YTick',1:4,'YTickLabel',labels,'XLim',[-5.5 15],'XTick',[0 5 10]);if k==2,a.YTickLabel={};end
 a.YGrid='off';a.XGrid='on';xline(a,0,'Color',[.2 .2 .2],'LineWidth',.7);
 for j=1:4,dx=.25;ha='left';if v(j)<0,dx=-.25;ha='right';end;text(a,v(j)+dx,j,sprintf('%+.3f',v(j)),'FontSize',7.5,'VerticalAlignment','middle','HorizontalAlignment',ha);end
 xlabel(a,'相对同期节省 / 万元');if k==1,panel(a,'a','日前  基础执行器');else,panel(a,'b','滚动  基础执行器');end
end
a=place(f,[.14 .15 .35 .25]);imagesc(a,2:12,1:4,D.monthly_saving);set(a,'YDir','reverse','XLim',[1.5 12.5],'YLim',[.5 4.5],'YTick',1:4,'YTickLabel',{'问题二','问题三','四 日前','四 滚动'},'XTick',[2 4 6 8 10 12]);colormap(a,ramp([1 1 1;hex('#B7B7EB');C.gru],128));clim(a,[0 3]);a.XGrid='off';a.YGrid='off';xlabel(a,'月份');panel(a,'c','价值控制月度节省');
cb=colorbar(a,'Position',[.51 .15 .012 .25]);cb.FontSize=7;cb.Label.String='万元';
b=place(f,[.67 .15 .26 .25]);errorbar(b,D.saving,1:4,D.saving-D.saving_ci(:,1)',D.saving_ci(:,2)'-D.saving,'horizontal','o','Color',C.gru,'MarkerFaceColor',C.gru,'MarkerSize',4,'CapSize',4,'LineWidth',1);
set(b,'YDir','reverse','YTick',1:4,'YTickLabel',{'二','三','四日前','四滚动'},'XLim',[0 24],'XTick',[0 10 20],'YLim',[.5 4.5]);b.YGrid='off';b.XGrid='on';xlabel(b,'全年节省 / 万元');panel(b,'d','区块重采样95%区间');
savefigs(f,out,'q4_cost');

f=makefig(2.7);a=place(f,[.12 .24 .48 .61]);colors=[C.base;C.grid;C.gru];styles={'--',':','-'};
for k=1:3,plot(a,32:365,cumsum(D.bound_daily(k,:)),'Color',colors(k,:),'LineStyle',styles{k},'LineWidth',1.2);end
set(a,'XLim',[32 365],'XTick',[32 121 213 305],'XTickLabel',{'2月','5月','8月','11月'});ylabel(a,'累计名义费用差距 / 万元');panel(a,'a','共同可行域的逐日最优值差距');
legend(a,{'同期','岭回归','GRU'},'Location','northwest','FontSize',7.5);
b=place(f,[.74 .24 .21 .61]);v=sum(D.bound_daily,2);bar(b,1:3,v,.53,'FaceColor','flat','CData',colors,'EdgeColor','none');set(b,'XTick',1:3,'XTickLabel',{'同期','岭回归','GRU'},'YLim',[0 18],'FontSize',7.5);ylabel(b,'全年差距 / 万元');panel(b,'b','剩余改进上限');
for i=1:3,text(b,i,v(i)+.45,sprintf('%.2f',v(i)),'HorizontalAlignment','center','FontSize',8);end
text(b,2,17.1,sprintf('GRU  %.3f%%',100*v(3)/D.bound_nominal(3)),'HorizontalAlignment','center','FontSize',9,'Color',C.gru);
savefigs(f,out,'q4_bound');
v6_focus_figures(root,skillRoot);
disp('V6 MATLAB figures completed');
end

function f=makefig(h)
f=figure('Visible','off','Color','w');apply_publication_style(f,"zh","report");
f.Position(3:4)=[6.3 h];set(f,'DefaultAxesFontName','Microsoft YaHei','DefaultAxesFontSize',9,'DefaultTextFontName','Microsoft YaHei','DefaultTextInterpreter','none','DefaultLegendInterpreter','none','DefaultAxesTickLabelInterpreter','none');
end
function ax=place(f,pos)
ax=axes(f,'Position',pos);hold(ax,'on');ax.FontSize=8.5;ax.LineWidth=.65;ax.TickDir='out';ax.Box='off';ax.YGrid='on';ax.GridColor=[.82 .85 .89];ax.GridAlpha=.5;ax.Layer='top';
end
function panel(ax,letter,label)
text(ax,0,1.10,[letter '  ' label],'Units','normalized','FontSize',8.5,'FontWeight','bold','VerticalAlignment','bottom');
end
function c=hex(s)
c=sscanf(s(2:end),'%2x%2x%2x',[1 3])/255;
end
function map=ramp(colors,n)
map=interp1(linspace(0,1,size(colors,1)),colors,linspace(0,1,n));
end
function box(ax,p,label)
rectangle(ax,'Position',p,'EdgeColor',[.15 .15 .15],'FaceColor','w','LineWidth',.75,'Curvature',0);
text(ax,p(1)+p(3)/2,p(2)+p(4)/2,label,'HorizontalAlignment','center','VerticalAlignment','middle','FontSize',8.4,'Color','k','FontName','SimSun');
end
function arrow(ax,a,b,ls)
if nargin<4,ls='-';end
plot(ax,[a(1) b(1)],[a(2) b(2)],['k' ls],'LineWidth',.65);
v=(b-a)/norm(b-a);n=[-v(2) v(1)];tip=b;u=b-v*1.15;
patch(ax,[tip(1) u(1)+n(1)*.5 u(1)-n(1)*.5],[tip(2) u(2)+n(2)*.5 u(2)-n(2)*.5],'k','EdgeColor','none');
end
function savefigs(f,out,name)
issues=audit_publication_figure(f);
fid=fopen(fullfile(out,[name '_audit.json']),'w','n','UTF-8');fwrite(fid,jsonencode(issues),'char');fclose(fid);
% Record geometric warnings for visual inspection; invisible flowchart axes
% and explicit manual panels can trigger the generic TightInset heuristic.
export_publication_figure(f,string(fullfile(out,name)),360,true,false);
exportgraphics(f,fullfile(out,[name '.pdf']),'ContentType','vector');
savefig(f,fullfile(out,[name '.fig']));close(f);disp(['Exported ' name]);
end
